from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy

from app.agents.regime_engine import RegimeEngine
from app.agents.risk_engine import RiskEngine
from app.agents.signal_engine import SignalEngine


@dataclass(frozen=True)
class _ForecastProxy:
    action: str
    price: float
    suggested_tp: float
    suggested_sl: float
    indicators: dict


class CompoundScalpingStrategy(IStrategy):
    """Freqtrade execution shell using the pre-migration scalping decision brain."""

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

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.regime_engine = RegimeEngine()
        self.signal_engine = SignalEngine(min_score=70.0, fee_percent=0.30, slippage_percent=0.05)
        self.risk_engine = RiskEngine()

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

    @staticmethod
    def _support_resistance_score(prices: list[float]) -> float:
        if len(prices) < 10:
            return 0.5
        window = prices[-30:]
        low, high, price = min(window), max(window), prices[-1]
        if high <= low:
            return 0.5
        position = (price - low) / (high - low)
        return 0.7 if position >= 0.65 else (0.35 if position <= 0.20 else 0.5)

    @staticmethod
    def _btc_return_percent(dataframe: DataFrame) -> float:
        if len(dataframe) < 2:
            return 0.0
        previous = float(dataframe["close"].iloc[-2])
        current = float(dataframe["close"].iloc[-1])
        return ((current / previous) - 1.0) * 100 if previous > 0 else 0.0

    def _build_brain(self, dataframe: DataFrame) -> DataFrame:
        prices = [float(value) for value in dataframe["close"].dropna().tolist()]
        if len(prices) < self.startup_candle_count:
            return dataframe

        regime = self.regime_engine.classify(prices, 0.0)
        if regime is None:
            return dataframe

        current = float(dataframe["close"].iloc[-1])
        atr = float(dataframe["atr"].iloc[-1]) if dataframe["atr"].iloc[-1] == dataframe["atr"].iloc[-1] else 0.0
        momentum_percent = float(dataframe["momentum_percent"].iloc[-1])
        trend_up = (
            float(dataframe["ema_fast"].iloc[-1]) > float(dataframe["ema_slow"].iloc[-1])
            and regime.name == "TREND_UP"
        )
        forecast_action = "buy" if trend_up and 52 <= float(dataframe["rsi"].iloc[-1]) <= 68 else "hold"

        # Keep the old expected-edge gate, but use an ATR-aware target so a valid
        # 1-minute setup is not rejected merely because the static ROI is smaller.
        target_percent = max(1.20, min(2.50, (atr / current * 100 * 1.5) if current > 0 else 1.20))
        suggested_tp = current * (1.0 + target_percent / 100)
        suggested_sl = current * (1.0 - max(0.80, min(1.20, (atr / current * 100) if current > 0 else 0.80)) / 100)

        forecast = _ForecastProxy(
            action=forecast_action,
            price=current,
            suggested_tp=suggested_tp,
            suggested_sl=suggested_sl,
            indicators={"momentum_percent": momentum_percent},
        )

        spread_percent = float(dataframe["spread_bps"].iloc[-1]) / 100.0
        book_imbalance = float(dataframe["orderbook_imbalance"].iloc[-1])
        if book_imbalance != book_imbalance:
            book_imbalance = 0.0
        liquidity_score = min(1.0, max(0.0, float(dataframe["volume_ratio"].iloc[-1]) / 2.0))
        decision = self.signal_engine.evaluate(
            forecast,
            regime,
            spread_percent,
            book_imbalance,
            self._btc_return_percent(dataframe),
            liquidity_score,
            self._support_resistance_score(prices),
            regime.data_quality,
            cooldown=False,
            exposure_available=True,
        )

        dataframe.loc[dataframe.index[-1], "regime_name"] = regime.name
        dataframe.loc[dataframe.index[-1], "regime_strength"] = regime.trend_strength
        dataframe.loc[dataframe.index[-1], "regime_volatility"] = regime.realized_vol_percent
        dataframe.loc[dataframe.index[-1], "signal_score"] = decision.score
        dataframe.loc[dataframe.index[-1], "expected_edge_percent"] = decision.expected_edge_percent
        dataframe.loc[dataframe.index[-1], "signal_action"] = decision.action
        dataframe.loc[dataframe.index[-1], "signal_reason"] = ",".join(decision.reasons)
        dataframe.loc[dataframe.index[-1], "btc_lead_percent"] = self._btc_return_percent(dataframe)
        dataframe.loc[dataframe.index[-1], "risk_multiplier"] = 1.0
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"].replace(0, float("nan"))
        dataframe["momentum_percent"] = dataframe["close"].pct_change(3) * 100

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
                pass

        return self._build_brain(dataframe)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        runmode = getattr(getattr(self.dp, "runmode", None), "value", "") if self.dp else ""
        live_mode = runmode in ("live", "dry_run")

        trend = dataframe["ema_fast"] > dataframe["ema_slow"]
        momentum = dataframe["rsi"].between(52, 68)
        strength = dataframe["adx"] > 18
        volume = dataframe["volume_ratio"] > 1.20

        if live_mode:
            book = dataframe["orderbook_imbalance"].fillna(-1) > 0.05
            spread = dataframe["spread_bps"].fillna(999) < 30
        else:
            book = dataframe["orderbook_imbalance"].fillna(0) > -1
            spread = dataframe["spread_bps"].fillna(0) < 999

        brain_open = dataframe["signal_action"] == "OPEN"
        score = dataframe["signal_score"].fillna(0)
        edge = dataframe["expected_edge_percent"].fillna(-999)

        dataframe.loc[
            brain_open & (score >= 70) & (edge > 0) & trend & momentum & strength & volume & book & spread,
            ["enter_long", "enter_tag"],
        ] = (1, "legacy_brain_open")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                | (dataframe["rsi"] > 74)
                | (dataframe["signal_action"] == "NO_TRADE")
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "brain_exit")
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Apply the reusable risk controller to execution-quality sizing.

        Freqtrade remains responsible for account-level loss/drawdown protections;
        this callback uses the shared risk engine for the information available at
        order time, especially spread-based size reduction.
        """
        spread_percent = 0.0
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            if not dataframe.empty:
                spread_percent = float(dataframe["spread_bps"].iloc[-1]) / 100.0
                if spread_percent != spread_percent:
                    spread_percent = 0.0
        except Exception:
            pass

        try:
            equity = float(self.wallets.get_total_stake_amount())
        except Exception:
            equity = float(proposed_stake)
        equity = max(equity, 1.0)
        risk = self.risk_engine.evaluate(
            daily_pnl=0.0,
            daily_start_balance=equity,
            equity=equity,
            peak_equity=equity,
            open_risk_percent=0.0,
            loss_streak=0,
            spread_percent=spread_percent,
        )
        if not risk.allowed:
            return 0.0
        return min(max_stake, max(0.0, proposed_stake * risk.risk_multiplier))
