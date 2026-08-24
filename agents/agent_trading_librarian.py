"""Trading Knowledge Librarian.

Advisory knowledge service for the trading agents. It keeps a curated local
library of trading/scalping principles and can refresh public educational URLs.
It never places orders and its output must be validated against live market data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
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
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/wealth-management/scalping-day-trading-technique/", ["scalping","intraday","execution"]),
            KnowledgeEntry("risk", "Risk-first trading", [
                "Define an invalidation point before entering a trade.",
                "Reduce position size as volatility or execution uncertainty rises.",
                "Include fees, spread and slippage before judging whether a small move is profitable."],
                "Trading risk principles", "https://corporatefinanceinstitute.com/resources/capital_markets/volatility-quote-trading/", ["risk","position sizing","volatility"]),
            KnowledgeEntry("momentum", "Momentum confirmation", [
                "Momentum measures strength of movement but does not guarantee continuation.",
                "Momentum entries are stronger when price structure, trend and volume agree.",
                "Do not chase a sharp move without a defined invalidation level."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/capital_markets/falling-knife/", ["momentum","trend","breakout","reversal"]),
            KnowledgeEntry("vwap", "VWAP context", [
                "VWAP is a volume-weighted price benchmark for intraday context.",
                "Price above or below VWAP can support directional bias, but VWAP is not a standalone predictor."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/equities/net-volume/", ["vwap","volume","intraday"]),
            KnowledgeEntry("atr", "ATR and volatility-aware exits", [
                "ATR estimates recent price range and can adapt stop distance to volatility.",
                "Higher volatility generally calls for smaller size when risk per trade is fixed."],
                "Corporate Finance Institute", "https://corporatefinanceinstitute.com/resources/capital_markets/keltner-channel/", ["atr","volatility","stop loss"]),
            KnowledgeEntry("candlestick", "Pin-bar context", [
                "A pin bar shows rejection of a price area; context and confirmation matter more than the candle alone.",
                "Support/resistance and follow-through should be checked before treating a reversal candle as an entry."],
                "Corporate Finance Institute", "https://cdn.corporatefinanceinstitute.com/assets/The-Complete-Guide-to-Trading.pdf", ["candlestick","pin bar","reversal"]),
            KnowledgeEntry("indodax", "Indodax API conventions", [
                "Indodax markets use identifiers such as btc_idr while the bridge exposes BTC/IDR.",
                "Private permissions should exclude withdrawals; paper mode uses public market data without credentials."],
                "INDODAX API Documentation", "https://indodax.com/downloads/INDODAXCOM-API-DOCUMENTATION.pdf", ["indodax","api","btc/idr","security"]),
        ]

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
        return {"query": query, "knowledge": self.retrieve(query, limit),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "advisory_only": True,
                "instruction": "Validate knowledge against current market data and risk controls."}

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
