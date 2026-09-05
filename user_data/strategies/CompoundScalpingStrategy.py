from __future__ import annotations

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class CompoundScalpingStrategy(IStrategy):
    """Conservative 1m spot strategy foundation for the compound-scalping engine.

    The execution engine remains Freqtrade. Higher-level signal/risk agents can later
    enrich this strategy without changing the exchange execution layer.
    """

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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > dataframe["volume_mean"] * 1.20)
                & (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["rsi"] > 52)
                & (dataframe["rsi"] < 68)
                & (dataframe["adx"] > 18)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "trend_volume_scalp")
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
