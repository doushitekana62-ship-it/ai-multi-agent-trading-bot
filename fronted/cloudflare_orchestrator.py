"""Cloudflare-safe adapter around the existing multi-agent Orchestrator.

The production Orchestrator was written for CPython and uses asyncio.to_thread.
Python Workers do not provide functional threading, so this adapter preserves
all existing agent/orchestration logic while invoking the synchronous agents
on the Worker event loop.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.orchestrator import Orchestrator


class CloudflareOrchestrator(Orchestrator):
    """Run the existing Orchestrator without CPython worker threads."""

    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        unified_snapshot: Optional[Any],
    ) -> Tuple[Optional[Any], Optional[Any]]:
        if unified_snapshot:
            market_data["current_price"] = unified_snapshot.current_price
            market_data["_unified_snapshot"] = unified_snapshot
        try:
            sentiment_result = self.sentiment_agent.analyze(symbol, market_data)
        except Exception:
            sentiment_result = None
        try:
            technical_result = self.technical_agent.analyze(symbol, market_data)
        except Exception:
            technical_result = None
        if unified_snapshot:
            if sentiment_result is not None and hasattr(sentiment_result, "current_price"):
                sentiment_result.current_price = unified_snapshot.current_price
            if technical_result is not None and hasattr(technical_result, "current_price"):
                technical_result.current_price = unified_snapshot.current_price
        return sentiment_result, technical_result

    async def _run_decision(self, symbol, sentiment, technical, market_data, unified_snapshot):
        try:
            if unified_snapshot:
                market_data["current_price"] = unified_snapshot.current_price
            return self.decision_agent.analyze(symbol, sentiment, technical, market_data)
        except Exception:
            return None

    async def _run_forecast(self, symbol, sentiment, technical, market_data, unified_snapshot):
        try:
            if unified_snapshot:
                market_data["current_price"] = unified_snapshot.current_price
            return self.forecast_agent.analyze(symbol, sentiment, technical, market_data)
        except Exception:
            return None

    async def _run_reflection(self, symbol, market_data, unified_snapshot):
        try:
            trades = market_data.get("recent_trades", [])
            if not isinstance(trades, list):
                trades = []
            return self.reflector_agent.analyze(symbol, trades, None)
        except Exception:
            return None
