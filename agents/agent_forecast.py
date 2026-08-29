"""Short-horizon probabilistic forecast specialist.

Forecast is evidence, not an execution decision. Horizons are market bars,
not days, so the same agent can be used for 1m scalping context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from core.signal_contract import SignalStatus, safe_float, utc_age_seconds


@dataclass
class PricePrediction:
    timestamp: datetime
    predicted_price: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    confidence: float
    horizon: str
    predicted_change_percent: float = 0.0


@dataclass
class ForecastResult:
    symbol: str
    timestamp: datetime
    current_price: float
    short_term: PricePrediction
    medium_term: PricePrediction
    long_term: PricePrediction
    bullish_path: List[float]
    bearish_path: List[float]
    most_likely_path: List[float]
    scenarios: Dict[str, Any]
    primary_trend: str
    trend_strength: float
    next_move_probability: Dict[str, float]
    expected_high: float
    expected_low: float
    expected_range: Dict[str, float]
    key_resistance: List[float]
    key_support: List[float]
    summary: str
    recommendations: List[str]
    model_predictions: Dict[str, List[float]]
    model_weights: Dict[str, float]
    model_status: Dict[str, str]
    data_quality: Dict[str, float]
    model_agreement: float
    forecast_score: float
    forecast_action: str
    warnings: List[str]
    direction: str = "NEUTRAL"
    score: float = 0.0
    confidence: float = 0.0
    timeframe: str = "1m-15m"
    evidence: List[str] = field(default_factory=list)
    data_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_seconds: float = 0.0
    status: str = SignalStatus.OK.value
    limitations: List[str] = field(default_factory=list)


class ForecastAgent:
    """Lightweight, deterministic short-horizon forecaster."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.horizons = (int(cfg.get("short_bars", 3)), int(cfg.get("medium_bars", 8)), int(cfg.get("long_bars", 15)))
        self.max_age_seconds = float(cfg.get("max_age_seconds", 90))
        self.max_move = float(cfg.get("max_reasonable_move", 0.08))

    def analyze(self, symbol: str, sentiment_result: Any = None, technical_result: Any = None,
                market_data: Optional[Dict[str, Any]] = None) -> ForecastResult:
        data = market_data or {}; symbol = symbol.upper()
        price = safe_float(data.get("unified_price", data.get("current_price")))
        candles = self._candles(data); closes = np.asarray([c["close"] for c in candles], dtype=float)
        timestamp = data.get("timestamp", datetime.now(timezone.utc)); age = utc_age_seconds(timestamp)
        timeframe = str(data.get("timeframe", "1m"))
        if price <= 0 or len(closes) < 10:
            return self._unavailable(symbol, price, timeframe, "INSUFFICIENT_HISTORY", age)
        if age > self.max_age_seconds:
            return self._unavailable(symbol, price, timeframe, "STALE_MARKET_SNAPSHOT", age, SignalStatus.DEGRADED.value)

        returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
        short = self._trend_return(closes, min(3, len(closes)-1)); medium = self._trend_return(closes, min(8, len(closes)-1)); long = self._trend_return(closes, min(15, len(closes)-1))
        # Forecast is intentionally conservative: recent trend, mean reversion,
        # and volatility are combined rather than an unstable recursive ML model.
        drift = 0.55 * short + 0.30 * medium + 0.15 * long
        volatility = max(float(np.std(returns[-30:])), 0.0005)
        paths = {}
        for name, bars in zip(("short", "medium", "long"), self.horizons):
            paths[name] = self._path(price, drift, bars)
        pred_short = self._prediction(price, paths["short"], volatility, "SHORT")
        pred_medium = self._prediction(price, paths["medium"], volatility, "MEDIUM")
        pred_long = self._prediction(price, paths["long"], volatility, "LONG")
        forecast_return = pred_short.predicted_change_percent / 100
        score = float(np.clip(np.tanh(forecast_return / max(volatility * np.sqrt(self.horizons[0]), 0.001)), -1, 1))
        technical_score = safe_float(getattr(technical_result, "overall_score", 0.0))
        # Forecast may align with technical evidence but never dominate it.
        score = float(np.clip(score * 0.75 + technical_score * 0.25, -1, 1))
        direction = "BULLISH" if score >= 0.15 else "BEARISH" if score <= -0.15 else "NEUTRAL"
        confidence = float(np.clip(0.40 + abs(score) * 0.35 + min(len(closes)/150, 1)*0.15, 0.35, 0.78))
        probs = self._probabilities(score, volatility, returns)
        evidence = [f"short={short:+.3%}", f"medium={medium:+.3%}", f"long={long:+.3%}", f"volatility={volatility:.3%}", f"UP={probs['UP']:.0%}", f"DOWN={probs['DOWN']:.0%}"]
        action = "BUY" if score >= 0.35 else "SELL" if score <= -0.35 else "HOLD"
        return ForecastResult(
            symbol=symbol, timestamp=datetime.now(timezone.utc), current_price=price,
            short_term=pred_short, medium_term=pred_medium, long_term=pred_long,
            bullish_path=[price*(1+abs(drift))**i for i in range(1, self.horizons[2]+1)],
            bearish_path=[price*(1-abs(drift))**i for i in range(1, self.horizons[2]+1)],
            most_likely_path=paths["long"], scenarios={}, primary_trend=direction,
            trend_strength=abs(score), next_move_probability=probs,
            expected_high=max(paths["long"])*(1+volatility), expected_low=min(paths["long"])*(1-volatility),
            expected_range={"high": max(paths["long"])*(1+volatility), "low": min(paths["long"])*(1-volatility)},
            key_resistance=[], key_support=[], summary=f"Forecast {symbol}: {direction} score={score:+.2f}",
            recommendations=["Forecast is probabilistic evidence; Trader owns action."], model_predictions=paths,
            model_weights={"trend": 1.0}, model_status={"short_horizon": "OK"}, data_quality={"history": min(len(closes)/150,1.0)},
            model_agreement=1.0, forecast_score=score, forecast_action=action, warnings=[], direction=direction,
            score=score, confidence=confidence, timeframe=timeframe, evidence=evidence,
            data_timestamp=timestamp if isinstance(timestamp, datetime) else datetime.now(timezone.utc), data_age_seconds=age,
            status=SignalStatus.OK.value, limitations=["Forecast is not a guarantee and is not an execution signal."],
        )

    @staticmethod
    def _candles(data):
        raw = data.get("ohlcv", [])
        if not raw and data.get("_unified_snapshot") is not None:
            raw = getattr(data["_unified_snapshot"], "ohlcv_data", [])
        out=[]
        for c in raw or []:
            try:
                get=c.get if isinstance(c,dict) else lambda k,d=0:getattr(c,k,d)
                o,h,l,cl=map(float,(get("open"),get("high"),get("low"),get("close")))
                out.append({"open":o,"high":h,"low":l,"close":cl,"volume":safe_float(get("volume"))})
            except (TypeError,ValueError): pass
        return out

    @staticmethod
    def _trend_return(prices,n):
        return float(prices[-1]/prices[-n-1]-1) if n>0 and len(prices)>n and prices[-n-1]>0 else 0.0

    @staticmethod
    def _path(price, drift, bars):
        drift=float(np.clip(drift,-0.02,0.02)); return [price*((1+drift)**i) for i in range(1,bars+1)]

    def _prediction(self, price, path, vol, horizon):
        pred=float(path[-1] if path else price); change=(pred/price-1)*100
        change=float(np.clip(change,-self.max_move*100,self.max_move*100)); pred=price*(1+change/100)
        width=price*vol*np.sqrt(max(len(path),1))*1.5
        conf=float(np.clip(0.45+min(abs(change)/max(vol*100,0.1),2)*0.12,0.35,0.75))
        return PricePrediction(datetime.now(timezone.utc)+timedelta(minutes=max(1,len(path))),pred,max(0,pred-width),pred+width,conf,horizon,change)

    @staticmethod
    def _probabilities(score,vol,returns):
        strength=float(np.clip(abs(score)*1.4,0,0.9)); side=max(0.05,1-strength); up=0.5+score*0.35; down=0.5-score*0.35
        total=up+down+side; return {"UP":up/total,"DOWN":down/total,"SIDEWAYS":side/total}

    def _unavailable(self,symbol,price,timeframe,reason,age,status=SignalStatus.UNAVAILABLE.value):
        p=PricePrediction(datetime.now(timezone.utc),price,price,price,0.0,"UNAVAILABLE",0.0)
        return ForecastResult(symbol,datetime.now(timezone.utc),price,p,p,p,[],[],[],{},"NEUTRAL",0.0,{"UP":0.0,"DOWN":0.0,"SIDEWAYS":1.0},price,price,{"high":price,"low":price},[],[],f"Forecast unavailable: {reason}",[],{}, {},{}, {},0.0,0.0,"HOLD",[reason],direction="NEUTRAL",score=0.0,confidence=0.0,timeframe=timeframe,evidence=[reason],data_age_seconds=age,status=status,limitations=[reason])
