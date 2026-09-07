from __future__ import annotations

from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy

from app.agents.forecast_agent import ForecastAgent
from app.agents.regime_engine import RegimeEngine
from app.agents.risk_engine import RiskEngine
from app.agents.scalping_library import ScalpingLibrary


class CompoundScalpingStrategy(IStrategy):
    """Freqtrade execution shell around the pre-migration scalping brain."""

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1m"
    process_only_new_candles = True
    startup_candle_count = 200

    minimal_roi = {"0": 0.012, "5": 0.008, "15": 0.005, "30": 0.0}
    stoploss = -0.008
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    use_custom_roi = True
    use_custom_stoploss = True

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.forecast_agent = ForecastAgent()
        self.regime_engine = RegimeEngine()
        self.scalping_library = ScalpingLibrary(min_score=70.0, fee_percent=0.30, slippage_percent=0.05)
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
        # Development is intentionally fixed to BTC/IDR. When the pair universe
        # expands, this can be switched to an informative BTC/IDR dataframe.
        if len(dataframe) < 2:
            return 0.0
        previous = float(dataframe["close"].iloc[-2])
        current = float(dataframe["close"].iloc[-1])
        return ((current / previous) - 1.0) * 100 if previous > 0 else 0.0

    def _refresh_orderbook(self, dataframe: DataFrame, pair: str) -> None:
        dataframe.loc[dataframe.index[-1], "spread_bps"] = float("nan")
        dataframe.loc[dataframe.index[-1], "orderbook_imbalance"] = float("nan")
        runmode = getattr(getattr(self.dp, "runmode", None), "value", "") if self.dp else ""
        if not self.dp or runmode not in ("live", "dry_run"):
            return
        try:
            ob = self.dp.orderbook(pair, 10)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if not bids or not asks:
                return
            bid = float(bids[0][0])
            ask = float(asks[0][0])
            bid_volume = sum(float(level[1]) for level in bids)
            ask_volume = sum(float(level[1]) for level in asks)
            total = bid_volume + ask_volume
            dataframe.loc[dataframe.index[-1], "spread_bps"] = ((ask - bid) / bid) * 10000 if bid > 0 else float("nan")
            dataframe.loc[dataframe.index[-1], "orderbook_imbalance"] = ((bid_volume - ask_volume) / total) if total else 0.0
        except Exception:
            return

    def _build_brain(self, dataframe: DataFrame, pair: str) -> None:
        if len(dataframe) < self.startup_candle_count:
            return
        prices = [float(value) for value in dataframe["close"].dropna().tolist()]
        regime = self.regime_engine.classify(prices, 0.0)
        forecast = self.forecast_agent.analyze(dataframe)
        if regime is None or forecast is None:
            return

        spread_percent = float(dataframe["spread_bps"].iloc[-1]) / 100.0
        if spread_percent != spread_percent:
            spread_percent = 0.0
        book_imbalance = float(dataframe["orderbook_imbalance"].iloc[-1])
        if book_imbalance != book_imbalance:
            book_imbalance = 0.0
        liquidity_score = min(1.0, max(0.0, forecast.indicators.get("volume_ratio", 1.0) / 2.0))

        decision = self.scalping_library.evaluate(
            forecast=forecast,
            regime=regime,
            spread_percent=spread_percent,
            book_imbalance=book_imbalance,
            btc_return_percent=self._btc_return_percent(dataframe),
            liquidity_score=liquidity_score,
            support_resistance_score=self._support_resistance_score(prices),
            data_quality=regime.data_quality,
            cooldown=False,
            exposure_available=True,
        )

        last = dataframe.index[-1]
        dataframe.loc[last, "regime_name"] = regime.name
        dataframe.loc[last, "regime_strength"] = regime.trend_strength
        dataframe.loc[last, "regime_volatility"] = regime.realized_vol_percent
        dataframe.loc[last, "signal_score"] = decision.score
        dataframe.loc[last, "expected_edge_percent"] = decision.expected_edge_percent
        dataframe.loc[last, "signal_action"] = decision.action
        dataframe.loc[last, "signal_reason"] = ",".join(decision.reasons)
        dataframe.loc[last, "btc_lead_percent"] = self._btc_return_percent(dataframe)
        dataframe.loc[last, "forecast_confidence"] = forecast.confidence
        dataframe.loc[last, "forecast_tp_percent"] = (forecast.suggested_tp / forecast.price - 1) * 100
        dataframe.loc[last, "forecast_sl_percent"] = (1 - forecast.suggested_sl / forecast.price) * 100
        dataframe.loc[last, "risk_multiplier"] = 1.0

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
        self._refresh_orderbook(dataframe, metadata["pair"])
        self._build_brain(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        runmode = getattr(getattr(self.dp, "runmode", None), "value", "") if self.dp else ""
        live_mode = runmode in ("live", "dry_run")
        trend = dataframe["ema_fast"] > dataframe["ema_slow"]
        momentum = dataframe["rsi"].between(52, 68)
        strength = dataframe["adx"] > 18
        volume = dataframe["volume_ratio"] > 1.20
        legacy_score = trend.astype(int) * 25 + momentum.astype(int) * 20 + strength.astype(int) * 20 + volume.astype(int) * 15
        dataframe["legacy_score"] = legacy_score

        if live_mode:
            book = dataframe["orderbook_imbalance"].fillna(-1) > 0.05
            spread = dataframe["spread_bps"].fillna(999) < 30
            brain_open = dataframe["signal_action"].fillna("") == "OPEN"
            score = dataframe["signal_score"].fillna(0)
            edge = dataframe["expected_edge_percent"].fillna(-999)
            condition = brain_open & (score >= 70) & (edge > 0) & trend & momentum & strength & volume & book & spread
            tag = "legacy_brain_open"
        else:
            condition = legacy_score >= 70
            tag = "legacy_score_backtest"
        dataframe.loc[condition, ["enter_long", "enter_tag"]] = (1, tag)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"]) | (dataframe["rsi"] > 74),
            ["exit_long", "exit_tag"],
        ] = (1, "brain_exit")
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str, current_time: datetime, entry_tag: str | None, side: str, **kwargs) -> bool:
        """Re-run critical legacy gates immediately before every paper entry."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            if dataframe.empty or len(dataframe) < self.startup_candle_count:
                return False
            dataframe = dataframe.copy()
            self._refresh_orderbook(dataframe, pair)
            self._build_brain(dataframe, pair)
            return (
                dataframe["signal_action"].iloc[-1] == "OPEN"
                and float(dataframe["signal_score"].iloc[-1]) >= 70
                and float(dataframe["expected_edge_percent"].iloc[-1]) > 0
            )
        except Exception:
            return False

    def custom_roi(self, pair: str, trade, current_time: datetime, trade_duration: int, entry_tag: str | None, side: str, **kwargs) -> float | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            if dataframe.empty:
                return None
            price = float(dataframe["close"].iloc[-1])
            atr = float(dataframe["atr"].iloc[-1])
            if price <= 0 or atr <= 0:
                return None
            return max(0.012, min(0.025, (atr / price) * 1.8))
        except Exception:
            return None

    def custom_stoploss(self, pair: str, trade, current_time: datetime, current_rate: float, current_profit: float, after_fill: bool, **kwargs) -> float | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            if dataframe.empty or current_rate <= 0:
                return None
            atr = float(dataframe["atr"].iloc[-1])
            if atr <= 0:
                return None
            return max(0.008, min(0.012, atr / current_rate))
        except Exception:
            return None

    def custom_exit(self, pair: str, trade, current_time: datetime, current_profit: float, **kwargs):
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            if dataframe.empty:
                return None
            candle = dataframe.iloc[-1]
            if float(candle["ema_fast"]) < float(candle["ema_slow"]):
                return "trend_reversal"
            if float(candle["rsi"]) > 74:
                return "rsi_overbought"
            if current_profit > 0 and candle.get("signal_action", "WAIT") == "NO_TRADE":
                return "brain_no_trade"
            return None
        except Exception:
            return None

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
        """Apply the shared risk controller to execution-quality sizing."""
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
