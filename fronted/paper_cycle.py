"""Shared paper-trading cycle runner.

The same implementation is used by HTTP/manual triggers and the Durable
Object alarm. It never submits real exchange orders. The decision itself is
produced by the repository's existing multi-agent Orchestrator through the
Cloudflare Container adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone

import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator


def _json_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_json_number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_market_history(previous, current, limit=120):
    merged = []
    seen = set()
    for point in list(previous or []) + list(current or []):
        key = (str(point.get("timestamp") or point.get("date") or ""), str(point.get("price") or ""), str(point.get("amount") or ""), str(point.get("type") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(point)
    merged.sort(key=lambda item: _json_number(item.get("timestamp") or item.get("date")))
    return merged[-limit:]


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    """Run one guarded paper-only cycle through the full AI pipeline."""
    pair = cf_worker._clean_pair(pair)
    ok, _, reason = await state_api.begin_cycle()
    if not ok:
        state = await state_api.get_state()
        return {"ok": False, "reason": reason, "state": state_response(state) if state_response else state}

    try:
        scope = {"env": env, "query_string": f"pair={pair}".encode("latin-1")}
        market = await cf_worker._market_overview(scope)
        if not market.get("available") or _json_number(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}

        # The Worker cannot access DurableObjectStub.ctx. Keep the cycle input
        # RPC-safe: the current public trades are already enough to build the
        # bounded analysis window, while persistent trading state remains owned
        # exclusively by PaperTradingState.
        points = list(market.get("points") or [])
        history = _merge_market_history([], points, limit=120)

        ohlcv = []
        for point in history:
            price = _json_number(point.get("price"))
            if price <= 0:
                continue
            raw_timestamp = _json_number(point.get("timestamp") or point.get("date"))
            timestamp = datetime.fromtimestamp(raw_timestamp, tz=timezone.utc).isoformat() if raw_timestamp > 0 else datetime.now(timezone.utc).isoformat()
            ohlcv.append({"timestamp": timestamp, "open": price, "high": price, "low": price, "close": price, "volume": _json_number(point.get("amount"), 1.0)})

        symbol = market["pair"].upper().replace("_", "/")
        last_price = _json_number(market.get("last"))
        market_data = {
            "current_price": last_price,
            "unified_price": last_price,
            "price": last_price,
            "high_24h": _json_number(market.get("high")),
            "low_24h": _json_number(market.get("low")),
            "volume_24h": _json_number(market.get("volume")),
            "change_percent_24h": _json_number(market.get("recent_move")),
            "timeframe": "trade",
            "ohlcv": ohlcv,
            "recent_trades": points,
            "volatility": None,
            "data_quality_score": 0.85 if len(ohlcv) >= 80 else 0.55,
        }

        orchestrator = CloudflareOrchestrator({"min_confidence": 0.40, "max_position_size": 0.20, "debug_enabled": True}, env=env)
        result = await orchestrator.analyze(symbol, market_data)

        action = str(result.final_action or "HOLD").upper()
        if action == "STRONG_BUY":
            action = "BUY"
        elif action == "STRONG_SELL":
            action = "SELL"
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        confidence = _json_number(result.final_confidence)
        metadata = {
            "source": "multi_agent_orchestrator_container",
            "symbol": result.symbol,
            "action": action,
            "raw_action": str(result.final_action or "HOLD"),
            "confidence": confidence,
            "consensus_action": result.consensus_action,
            "consensus_score": _json_number(result.consensus_score),
            "votes": dict(result.agent_votes or {}),
            "market_scores": {k: _json_number(v) for k, v in dict(result.market_scores or {}).items()},
            "confidence_components": {k: _json_number(v) for k, v in dict(result.confidence_components or {}).items()},
            "position_size": _json_number(result.position_size),
            "stop_loss": _optional_json_number(result.stop_loss),
            "take_profit": _optional_json_number(result.take_profit),
            "execution_reason": result.execution_reason,
            "hold_reason": result.hold_reason,
            "summary": result.summary,
            "agents_invoked": ["Sentiment Agent", "Technical Agent", "Decision Agent", "Forecast Agent", "Reflector Agent"],
            "market_history_points": len(ohlcv),
            "created_at": result.timestamp.isoformat(),
        }

        payload = {
            "decision": action,
            "confidence": confidence,
            "symbol": symbol,
            "price": last_price,
            "reasoning": result.execution_reason or result.hold_reason or result.summary,
        }
        state = await state_api.record_cycle_payload(payload)
        return {"ok": True, "action": action, "raw_action": result.final_action, "confidence": confidence, "market": market, "orchestrator": metadata, "state": state_response(state) if state_response else state}
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_error: {exc}")
        return {"ok": False, "reason": "cycle_error", "error": str(exc), "state": state_response(state) if state_response else state}
