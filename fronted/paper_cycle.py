"""Shared paper-trading cycle runner.

The same implementation is used by HTTP/manual triggers and the Durable
Object alarm. It never submits real exchange orders. The decision itself is
produced by the repository's existing multi-agent Orchestrator.
"""
from __future__ import annotations

from datetime import datetime, timezone

import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    """Run one guarded paper-only cycle through the existing AI pipeline."""
    pair = cf_worker._clean_pair(pair)
    ok, _, reason = await state_api.begin_cycle()
    if not ok:
        state = await state_api.get_state()
        return {
            "ok": False,
            "reason": reason,
            "state": state_response(state) if state_response else state,
        }

    try:
        scope = {"env": env, "query_string": f"pair={pair}".encode("latin-1")}
        market = await cf_worker._market_overview(scope)
        if not market.get("available") or float(market.get("last") or 0) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {
                "ok": False,
                "reason": "market_data_unavailable",
                "state": state_response(state) if state_response else state,
            }

        points = list(market.get("points") or [])
        ohlcv = []
        for point in points:
            price = float(point.get("price") or 0)
            if price <= 0:
                continue
            ohlcv.append({
                "timestamp": datetime.fromtimestamp(
                    float(point.get("timestamp") or 0), tz=timezone.utc
                ).isoformat() if float(point.get("timestamp") or 0) > 0 else datetime.now(timezone.utc).isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": float(point.get("amount") or 1.0),
            })

        symbol = market["pair"].upper().replace("_", "/")
        market_data = {
            "current_price": float(market.get("last") or 0),
            "unified_price": float(market.get("last") or 0),
            "price": float(market.get("last") or 0),
            "high_24h": float(market.get("high") or 0),
            "low_24h": float(market.get("low") or 0),
            "volume_24h": float(market.get("volume") or 0),
            "change_percent_24h": float(market.get("recent_move") or 0),
            "timeframe": "trade",
            "ohlcv": ohlcv,
            "recent_trades": points,
            "volatility": None,
            "data_quality_score": 0.85 if len(ohlcv) >= 80 else 0.55,
        }

        orchestrator = CloudflareOrchestrator({
            "use_unified_data": False,
            "use_mimic_trader": True,
            "min_confidence": 0.40,
            "max_position_size": 0.20,
            "debug_enabled": True,
        })
        result = await orchestrator.analyze(symbol, market_data)

        action = str(result.final_action or "HOLD").upper()
        if action == "STRONG_BUY":
            action = "BUY"
        elif action == "STRONG_SELL":
            action = "SELL"
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        confidence = float(result.final_confidence or 0.0)
        metadata = {
            "source": "multi_agent_orchestrator",
            "symbol": result.symbol,
            "action": action,
            "raw_action": str(result.final_action or "HOLD"),
            "confidence": confidence,
            "consensus_action": result.consensus_action,
            "consensus_score": float(result.consensus_score or 0.0),
            "votes": dict(result.agent_votes or {}),
            "market_scores": dict(result.market_scores or {}),
            "confidence_components": dict(result.confidence_components or {}),
            "position_size": float(result.position_size or 0.0),
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "execution_reason": result.execution_reason,
            "hold_reason": result.hold_reason,
            "summary": result.summary,
            "agents_invoked": [
                "Sentiment Agent",
                "Technical Agent",
                "Decision Agent",
                "Forecast Agent",
                "Reflector Agent",
            ],
            "created_at": result.timestamp.isoformat(),
        }

        await state_api.ctx.storage.put("last_orchestrator", metadata)

        payload = {
            "decision": action,
            "confidence": confidence,
            "symbol": symbol,
            "price": float(market.get("last") or 0),
            "reasoning": result.execution_reason or result.hold_reason or result.summary,
        }
        state = await state_api.record_cycle_payload(payload)
        return {
            "ok": True,
            "action": action,
            "raw_action": result.final_action,
            "confidence": confidence,
            "market": market,
            "orchestrator": metadata,
            "state": state_response(state) if state_response else state,
        }
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_error: {exc}")
        return {
            "ok": False,
            "reason": "cycle_error",
            "error": str(exc),
            "state": state_response(state) if state_response else state,
        }
