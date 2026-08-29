"""Shared paper-trading cycle runner.

The same implementation is used by HTTP/manual triggers and the Durable
Object alarm. It never submits real exchange orders. FastAPI Cloud is the
preferred AI engine; the Worker adapter supplies a safe local fallback when
that service is unavailable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator
from js import fetch
from pyodide.ffi import to_js

EXECUTION_CONFIDENCE_THRESHOLD = 0.75


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
        key = (
            str(point.get("timestamp") or point.get("date") or ""),
            str(point.get("price") or ""),
            str(point.get("amount") or ""),
            str(point.get("type") or point.get("side") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(point)
    merged.sort(key=lambda item: _json_number(item.get("timestamp") or item.get("date")))
    return merged[-limit:]


async def _persist_decision(env, symbol, action, confidence, reasoning, result):
    """Persist every completed paper AI decision to Supabase without blocking execution."""
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    if not url or not key:
        return {"saved": False, "reason": "supabase_credentials_missing"}

    payload = {
        "symbol": str(symbol).upper(),
        "action": str(action).upper(),
        "confidence": max(0.0, min(100.0, _json_number(confidence) * 100.0)),
        "reasoning": str(reasoning or ""),
        "agent_votes": dict(getattr(result, "agent_votes", {}) or {}),
        "market_scores": {k: _json_number(v) for k, v in dict(getattr(result, "market_scores", {}) or {}).items()},
        "confidence_components": {k: _json_number(v) for k, v in dict(getattr(result, "confidence_components", {}) or {}).items()},
        "consensus_action": str(getattr(result, "consensus_action", "HOLD") or "HOLD").upper(),
        "consensus_score": _json_number(getattr(result, "consensus_score", 0.0)),
        "position_size": _json_number(getattr(result, "position_size", 0.0)),
        "stop_loss": _optional_json_number(getattr(result, "stop_loss", None)),
        "take_profit": _optional_json_number(getattr(result, "take_profit", None)),
        "engine_source": str(getattr(result, "engine_source", "") or ""),
        "engine_warning": getattr(result, "engine_warning", None),
    }
    try:
        response = await fetch(
            f"{url}/rest/v1/decisions",
            to_js({
                "method": "POST",
                "headers": {
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                },
                "body": json.dumps(payload, separators=(",", ":")),
            }),
        )
        status = int(response.status)
        text = await response.text()
        if status < 200 or status >= 300:
            return {"saved": False, "reason": f"supabase_http_{status}", "detail": text[:500]}
        try:
            rows = json.loads(text)
        except Exception:
            rows = []
        row = rows[0] if isinstance(rows, list) and rows else {}
        return {"saved": True, "id": row.get("id")}
    except Exception as exc:
        return {"saved": False, "reason": type(exc).__name__}


async def _persist_trade(env, trade, decision_id=None):
    """Persist an executed paper trade to Supabase when a BUY/SELL was actually filled."""
    if not trade:
        return {"saved": False, "reason": "no_trade"}
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    if not url or not key:
        return {"saved": False, "reason": "supabase_credentials_missing"}
    payload = {
        "decision_id": decision_id,
        "symbol": trade.get("symbol"),
        "action": trade.get("action"),
        "price": _json_number(trade.get("price")),
        "quantity": _json_number(trade.get("quantity")),
        "pnl": _json_number(trade.get("pnl")),
        "confidence": _json_number(trade.get("confidence", 0.0)) * 100.0,
        "status": "OPEN" if str(trade.get("action")).upper() == "BUY" else "CLOSED",
    }
    if payload["action"] == "BUY":
        payload["entry_price"] = payload["price"]
    else:
        payload["exit_price"] = payload["price"]
    try:
        response = await fetch(
            f"{url}/rest/v1/trades",
            to_js({
                "method": "POST",
                "headers": {
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                },
                "body": json.dumps(payload, separators=(",", ":")),
            }),
        )
        status = int(response.status)
        text = await response.text()
        if status < 200 or status >= 300:
            return {"saved": False, "reason": f"supabase_http_{status}", "detail": text[:500]}
        return {"saved": True}
    except Exception as exc:
        return {"saved": False, "reason": type(exc).__name__}


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    """Run one guarded paper-only cycle through the AI pipeline."""
    pair = cf_worker._clean_pair(pair)
    begin = await state_api.begin_cycle()
    if not isinstance(begin, dict):
        state = await state_api.get_state()
        return {"ok": False, "reason": "invalid_cycle_lock_response", "state": state_response(state) if state_response else state}
    if not begin.get("ok"):
        state = begin.get("state") or await state_api.get_state()
        return {"ok": False, "reason": begin.get("reason") or "cycle_start_rejected", "state": state_response(state) if state_response else state}

    try:
        scope = {"env": env, "query_string": f"pair={pair}".encode("latin-1")}
        market = await cf_worker._market_overview(scope)
        if not market.get("available") or _json_number(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}

        points = list(market.get("points") or [])
        previous_history = await state_api.get_paper_market_history()
        history = _merge_market_history(previous_history, points, limit=120)
        await state_api.set_paper_market_history(history)

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

        orchestrator = CloudflareOrchestrator({"min_confidence": EXECUTION_CONFIDENCE_THRESHOLD, "max_position_size": 0.10, "debug_enabled": True}, env=env)
        result = await orchestrator.analyze(symbol, market_data)

        raw_action = str(result.final_action or "HOLD").upper()
        action = raw_action
        if action == "STRONG_BUY":
            action = "BUY"
        elif action == "STRONG_SELL":
            action = "SELL"
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        confidence = _json_number(result.final_confidence)
        gate_passed = action in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD
        if action in {"BUY", "SELL"} and not gate_passed:
            action = "HOLD"
            reasoning = f"Execution gate blocked {raw_action}: confidence {confidence:.1%} is below the {EXECUTION_CONFIDENCE_THRESHOLD:.0%} threshold."
        else:
            reasoning = result.execution_reason or result.hold_reason or result.summary

        metadata = {
            "source": getattr(result, "engine_source", "fastapi_cloud"),
            "warning": getattr(result, "engine_warning", None),
            "symbol": result.symbol,
            "action": action,
            "raw_action": raw_action,
            "confidence": confidence,
            "execution_gate": {"threshold": EXECUTION_CONFIDENCE_THRESHOLD, "passed": gate_passed, "executed_action": action},
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
            "agents_invoked": list(dict(result.agent_votes or {}).keys()),
            "market_history_points": len(ohlcv),
            "created_at": result.timestamp.isoformat(),
        }
        await state_api.record_orchestrator(metadata)

        persistence = await _persist_decision(env, symbol, action, confidence, reasoning, result)
        payload = {
            "decision": action,
            "confidence": confidence,
            "symbol": symbol,
            "price": last_price,
            "reasoning": reasoning,
            "analysis": metadata,
        }
        state = await state_api.record_cycle_payload(payload)
        trade_persistence = {"saved": False, "reason": "no_trade"}
        trade = (state.get("last_decision") or {}).get("trade") if isinstance(state, dict) else None
        if trade:
            trade_persistence = await _persist_trade(env, trade, persistence.get("id"))
        cycle_result = {
            "ok": True,
            "action": action,
            "raw_action": result.final_action,
            "confidence": confidence,
            "market": market,
            "orchestrator": metadata,
            "persistence": {"decision": persistence, "trade": trade_persistence},
            "state": state_response(state) if state_response else state,
        }
        return cycle_result
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_error: {exc}")
        return {"ok": False, "reason": "cycle_error", "error": str(exc), "state": state_response(state) if state_response else state}
