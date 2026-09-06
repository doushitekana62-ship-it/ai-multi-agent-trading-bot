from __future__ import annotations

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class CompoundScalpingStrategy(IStrategy):
    """Conservative spot scalper with trend, volume, order-book and spread gates."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1m"
    process_only_new_candles = True
    startup_candle_count = 200

    minimal_roi = {"0": 0.006, "5": 0.004, "15": 0.002, "30": 0.0}
    stoploss = -0.008
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 30,
                "trade_limit": 3,
                "stop_duration_candles": 6,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 60,
                "trade_limit": 10,
                "stop_duration_candles": 12,
                "max_allowed_drawdown": 0.10,
                "calculation_mode": "equity",
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"].replace(0, float("nan"))

        dataframe["spread_bps"] = float("nan")
        dataframe["orderbook_imbalance"] = float("nan")
        runmode = getattr(getattr(self.dp, "runmode", None), "value", "") if self.dp else ""
        if self.dp and runmode in ("live", "dry_run"):
            try:
                ob = self.dp.orderbook(metadata["pair"], 10)
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                if bids and asks:
                    bid = float(bids[0][0])
                    ask = float(asks[0][0])
                    bid_volume = sum(float(level[1]) for level in bids)
                    ask_volume = sum(float(level[1]) for level in asks)
                    total = bid_volume + ask_volume
                    dataframe.loc[dataframe.index[-1], "spread_bps"] = ((ask - bid) / bid) * 10000 if bid > 0 else float("nan")
                    dataframe.loc[dataframe.index[-1], "orderbook_imbalance"] = ((bid_volume - ask_volume) / total) if total else 0.0
            except Exception:
                # A transient order-book failure must not crash the strategy.
                pass
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend = dataframe["ema_fast"] > dataframe["ema_slow"]
        momentum = dataframe["rsi"].between(52, 68)
        strength = dataframe["adx"] > 18
        volume = dataframe["volume_ratio"] > 1.20
        runmode = getattr(getattr(self.dp, "runmode", None), "value", "") if self.dp else ""

        # Orderbook/spread are live-only signals. Backtests must not invent them
        # from future data; they use the OHLCV signal score only.
        if runmode in ("live", "dry_run"):
            book = dataframe["orderbook_imbalance"].fillna(-1) > 0.05
            spread = dataframe["spread_bps"].fillna(999) < 30
            book_points = book.astype(int) * 15
            spread_points = spread.astype(int) * 5
        else:
            book = True
            spread = True
            book_points = 0
            spread_points = 0

        score = (
            trend.astype(int) * 25
            + momentum.astype(int) * 20
            + strength.astype(int) * 20
            + volume.astype(int) * 15
            + book_points
            + spread_points
        )
        dataframe["signal_score"] = score

        dataframe.loc[
            (dataframe["signal_score"] >= 70) & trend & momentum & strength & volume & book & spread,
            ["enter_long", "enter_tag"],
        ] = (1, "compound_score_orderflow" if runmode in ("live", "dry_run") else "compound_score_backtest")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                | (dataframe["rsi"] > 74)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "trend_reversal")
        return dataframe
