"""Trading Knowledge Librarian and deterministic market-pattern advisor.

The librarian is an advisory knowledge boundary. It does not place orders.
It supplies shared trading principles to the other agents and produces
structured, auditable candle/opportunity alerts from current market data.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests


@dataclass(frozen=True)
class KnowledgeEntry:
    topic: str
    title: str
    principles: List[str]
    source: str
    source_url: str
    tags: List[str]


class TradingLibrarianAgent:
    """Shared trading knowledge plus deterministic candle-context analysis."""

    LIBRARY_VERSION = "2026.08.candlestick-v1"

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.entries = self._default_library()
        self.last_refresh = None

    @staticmethod
    def _default_library() -> List[KnowledgeEntry]:
        return [
            KnowledgeEntry("scalping", "Scalping fundamentals", [
                "Scalping targets small short-duration price movements and requires precise entries and exits.",
                "Liquidity, spread, latency and execution quality matter because costs can consume small gains.",
                "Lower timeframe signals contain more noise and should be confirmed by market structure and risk controls."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/wealth-management/scalping-day-trading-technique/", ["scalping", "intraday", "execution"]),
            KnowledgeEntry("risk", "Risk-first trading", [
                "Define an invalidation point before entering a trade.",
                "Reduce position size as volatility or execution uncertainty rises.",
                "Include fees, spread and slippage before judging whether a small move is profitable."],
                "Trading risk principles", "https://corporatefinanceinstitute.com/resources/capital_markets/volatility-quote-trading/", ["risk", "position sizing", "volatility"]),
            KnowledgeEntry("momentum", "Momentum confirmation", [
                "Momentum measures strength of movement but does not guarantee continuation.",
                "Momentum entries are stronger when price structure, trend and volume agree.",
                "Do not chase a sharp move without a defined invalidation level."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/capital_markets/falling-knife/", ["momentum", "trend", "breakout", "reversal"]),
            KnowledgeEntry("volume", "Volume confirmation", [
                "Volume is confirmation, not a standalone directional forecast.",
                "Price/volume agreement increases the quality of a directional setup.",
                "Price/volume divergence is a warning that momentum may be weakening."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/capital_markets/obv/", ["volume", "obv", "confirmation", "divergence"]),
            KnowledgeEntry("candlestick", "Candlestick reading", [
                "A candle contains open, high, low and close; body size describes directional displacement while wicks describe rejected prices.",
                "Doji and small-body candles describe uncertainty and should not be treated as standalone entry signals.",
                "Bullish/bearish engulfing and rejection candles require context and follow-through confirmation."],
                "INDODAX Academy / CFI", "https://indodax.com/academy/en/indodax-academy-episode-2-the-easy-way-to-read-candlestick-charts/", ["candlestick", "ohlcv", "doji", "engulfing", "hammer"]),
            KnowledgeEntry("indodax", "Indodax public market data", [
                "Indodax exposes public ticker, trades and depth endpoints without an API key.",
                "The paper system must keep public market data separate from private trading credentials.",
                "Market symbols are normalized between exchange identifiers such as btc_idr and dashboard labels such as BTC/IDR."],
                "INDODAX API Documentation", "https://indodax.com/downloads/INDODAXCOM-API-DOCUMENTATION.pdf", ["indodax", "api", "public data", "security"]),
        ]

    @staticmethod
    def _number(value, default=0.0):
        try:
            number = float(value)
            if number != number or number in (float("inf"), float("-inf")):
                return default
            return number
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_candles(cls, candles: List[Dict]) -> List[Dict]:
        normalized = []
        for item in candles or []:
            if not isinstance(item, dict):
                continue
            o = cls._number(item.get("open"))
            h = cls._number(item.get("high"), o)
            l = cls._number(item.get("low"), o)
            c = cls._number(item.get("close"), o)
            v = max(0.0, cls._number(item.get("volume")))
            if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c):
                continue
            normalized.append({"timestamp": item.get("timestamp"), "open": o, "high": h, "low": l, "close": c, "volume": v})
        return normalized[-120:]

    @classmethod
    def analyze_candles(cls, candles: List[Dict], current_price: float = 0.0, high_24h: float = 0.0, low_24h: float = 0.0) -> Dict:
        """Detect high-value candle contexts without turning patterns into orders."""
        data = cls._normalize_candles(candles)
        if len(data) < 2:
            return {
                "library_version": cls.LIBRARY_VERSION,
                "available": False,
                "pattern": "INSUFFICIENT_DATA",
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "alerts": [],
                "candle_count": len(data),
            }

        last = data[-1]
        previous = data[-2]
        body = abs(last["close"] - last["open"])
        candle_range = max(last["high"] - last["low"], last["close"] * 1e-9)
        upper_wick = last["high"] - max(last["open"], last["close"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        avg_volume = sum(item["volume"] for item in data[-min(20, len(data)):]) / max(1, min(20, len(data)))
        volume_ratio = last["volume"] / avg_volume if avg_volume > 0 else 1.0

        prev_body = abs(previous["close"] - previous["open"])
        bullish_engulfing = (
            previous["close"] < previous["open"]
            and last["close"] > last["open"]
            and last["open"] <= previous["close"]
            and last["close"] >= previous["open"]
            and body >= max(prev_body, candle_range * 0.35)
        )
        bearish_engulfing = (
            previous["close"] > previous["open"]
            and last["close"] < last["open"]
            and last["open"] >= previous["close"]
            and last["close"] <= previous["open"]
            and body >= max(prev_body, candle_range * 0.35)
        )
        doji = body <= candle_range * 0.10
        hammer = lower_wick >= body * 2 and upper_wick <= max(body * 0.75, candle_range * 0.10)
        shooting_star = upper_wick >= body * 2 and lower_wick <= max(body * 0.75, candle_range * 0.10)
        long_bull = last["close"] > last["open"] and body >= candle_range * 0.65
        long_bear = last["close"] < last["open"] and body >= candle_range * 0.65

        recent = data[-5:]
        trend_delta = recent[-1]["close"] - recent[0]["close"]
        trend_direction = "BUY" if trend_delta > 0 else "SELL" if trend_delta < 0 else "NEUTRAL"

        pattern = "NORMAL"
        direction = "NEUTRAL"
        pattern_strength = 0.35
        message = "No high-priority candlestick opportunity detected."
        if bullish_engulfing:
            pattern, direction, pattern_strength = "BULLISH_ENGULFING", "BUY", 0.78
            message = "Bullish engulfing detected; wait for context/follow-through confirmation."
        elif bearish_engulfing:
            pattern, direction, pattern_strength = "BEARISH_ENGULFING", "SELL", 0.78
            message = "Bearish engulfing detected; wait for context/follow-through confirmation."
        elif hammer:
            pattern, direction, pattern_strength = "HAMMER_REJECTION", "BUY", 0.64
            message = "Lower-price rejection detected; confirmation from subsequent price action is required."
        elif shooting_star:
            pattern, direction, pattern_strength = "SHOOTING_STAR_REJECTION", "SELL", 0.64
            message = "Upper-price rejection detected; confirmation from subsequent price action is required."
        elif doji:
            pattern, direction, pattern_strength = "DOJI_INDECISION", "NEUTRAL", 0.48
            message = "Doji/indecision detected; do not treat it as a standalone entry signal."
        elif long_bull:
            pattern, direction, pattern_strength = "LONG_BULLISH_BODY", "BUY", 0.58
            message = "Strong bullish body detected; continuation still needs volume/structure confirmation."
        elif long_bear:
            pattern, direction, pattern_strength = "LONG_BEARISH_BODY", "SELL", 0.58
            message = "Strong bearish body detected; continuation still needs volume/structure confirmation."

        volume_confirmed = volume_ratio >= 1.20
        range_position = 50.0
        if high_24h > low_24h > 0 and current_price > 0:
            range_position = max(0.0, min(100.0, ((current_price - low_24h) / (high_24h - low_24h)) * 100.0))

        alerts = []
        if pattern != "NORMAL":
            confirmation = "Volume confirms the move." if volume_confirmed else "Volume confirmation is weak; treat this as an alert, not an entry."
            confidence = min(0.95, pattern_strength + (0.10 if volume_confirmed else 0.0) + (0.06 if direction == trend_direction else 0.0))
            alerts.append({
                "id": f"{pattern.lower()}:{last.get('timestamp') or last['close']}",
                "type": "CANDLE_PATTERN",
                "title": pattern.replace("_", " "),
                "message": f"{message} {confirmation}",
                "direction": direction,
                "confidence": confidence,
                "volume_ratio": volume_ratio,
                "requires_confirmation": True,
            })

        if volume_confirmed and direction in {"BUY", "SELL"}:
            alerts.append({
                "id": f"volume-confirmation:{last.get('timestamp') or last['close']}",
                "type": "VOLUME_CONFIRMATION",
                "title": "Volume Confirmation",
                "message": f"Current candle volume is {volume_ratio:.1f}x the recent average.",
                "direction": direction,
                "confidence": min(0.90, 0.55 + min(0.30, (volume_ratio - 1.0) * 0.25)),
            })

        if range_position >= 90:
            alerts.append({
                "id": f"range-high:{round(range_position)}",
                "type": "RANGE_CONTEXT",
                "title": "Near 24H High",
                "message": "Price is near the 24-hour high; breakout and rejection scenarios should both be monitored.",
                "direction": "BUY" if direction == "BUY" else "NEUTRAL",
                "confidence": 0.55,
            })
        elif range_position <= 10:
            alerts.append({
                "id": f"range-low:{round(range_position)}",
                "type": "RANGE_CONTEXT",
                "title": "Near 24H Low",
                "message": "Price is near the 24-hour low; reversal and continuation scenarios should both be monitored.",
                "direction": "SELL" if direction == "SELL" else "NEUTRAL",
                "confidence": 0.55,
            })

        opportunity = bool(pattern != "NORMAL" and direction in {"BUY", "SELL"} and volume_confirmed and direction == trend_direction)
        return {
            "library_version": cls.LIBRARY_VERSION,
            "available": True,
            "pattern": pattern,
            "direction": direction,
            "confidence": min(0.95, pattern_strength + (0.10 if volume_confirmed else 0.0)),
            "volume_ratio": volume_ratio,
            "range_position": range_position,
            "trend_direction": trend_direction,
            "opportunity": opportunity,
            "alerts": alerts[:4],
            "candle_count": len(data),
        }

    def retrieve(self, query: str, limit: int = 3) -> List[Dict]:
        terms = {t for t in re.findall(r"[a-z0-9/+-]+", query.lower()) if len(t) > 2}
        ranked = []
        for entry in self.entries:
            text = " ".join([entry.topic, entry.title, *entry.tags, *entry.principles]).lower()
            score = sum(1 for term in terms if term in text)
            if score:
                ranked.append((score, entry))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [{**asdict(entry), "relevance": score} for score, entry in ranked[:max(1, limit)]]

    def advise(self, query: str, limit: int = 3) -> Dict:
        return {
            "query": query,
            "knowledge": self.retrieve(query, limit),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "library_version": self.LIBRARY_VERSION,
            "advisory_only": True,
            "instruction": "Validate knowledge against current market data, candle context and deterministic risk controls.",
        }

    def refresh_from_urls(self, urls: Optional[List[str]] = None) -> Dict:
        urls = urls or [entry.source_url for entry in self.entries]
        results = []
        for url in urls:
            try:
                response = requests.get(url, timeout=8, headers={"User-Agent": "AI-Trading-Bot-Knowledge-Librarian/1.0"})
                response.raise_for_status()
                text = re.sub(r"\s+", " ", response.text)
                results.append({"url": url, "ok": True, "content_length": len(text)})
            except Exception as exc:
                results.append({"url": url, "ok": False, "error": str(exc)})
        self.last_refresh = datetime.now(timezone.utc).isoformat()
        return {"refreshed_at": self.last_refresh, "sources": results}
