"""Shared guarded paper-trading cycle runner."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator
from js import fetch
from pyodide.ffi import to_js

EXECUTION_CONFIDENCE_THRESHOLD = 0.65
AGGRESSIVE_SIGNAL_THRESHOLD = 0.10
MAX_POSITION_SIZE = 0.10


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


def _history_move_percent(history):
    prices = [_json_number(point.get("price")) for point in history or []]
    prices = [price for price in prices if price > 0]
    if len(prices) < 2 or prices[0] <= 0:
        return None
    return ((prices[-1] - prices[0]) / prices[0]) * 100.0


def _supabase(env):
    return str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/"), str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()


async def _post_supabase(env, table, payload):
    url, key = _supabase(env)
    if not url or not key:
        return {"saved": False, "reason": "supabase_credentials_missing"}
    try:
        response = await fetch(
            f"{url}/rest/v1/{table}",
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
            return {"saved": True, "id": rows[0].get("id") if isinstance(rows, list) and rows else None}
        except Exception:
            return {"saved": True}
    except Exception as exc:
        return {"saved": False, "reason": type(exc).__name__}


async def _persist_decision(env, symbol, action, confidence, reasoning, result):
    payload = {
        "symbol": str(symbol).upper(),
        "action": str(action).upper(),
        "confidence": max(0, min(100, _json_number(confidence) * 100)),
        "reasoning": str(reasoning or ""),
        "agent_votes": dict(getattr(result, "agent_votes", {}) or {}),
        "market_scores": {k: _json_number(v) for k, v in dict(getattr(result, "market_scores", {}) or {}).items()},
        "confidence_components": {k: _json_number(v) for k, v in dict(getattr(result, "confidence_components", {}) or {}).items()},
        "consensus_action": str(getattr(result, "consensus_action", "HOLD") or "HOLD").upper(),
        "consensus_score": _json_number(getattr(result, "consensus_score", 0)),
        "position_size": _json_number(getattr(result, "position_size", 0)),
        "stop_loss": _optional_json_number(getattr(result, "stop_loss", None)),
        "take_profit": _optional_json_number(getattr(result, "take_profit", None)),
        "engine_source": str(getattr(result, "engine_source", "") or ""),
        "engine_warning": getattr(result, "engine_warning", None),
    }
    return await _post_supabase(env, "decisions", payload)


async def _persist_trade(env, trade, decision_id=None):
    if not trade:
        return {"saved": False, "reason": "no_trade"}
    action = str(trade.get("action") or "").upper()
    price = _json_number(trade.get("price"))
    qty = _json_number(trade.get("quantity"))
    payload = {
        "decision_id": decision_id,
        "symbol": trade.get("symbol"),
        "action": action,
        "price": price,
        "quantity": qty,
        "pnl": _json_number(trade.get("pnl")),
        "confidence": _json_number(trade.get("confidence", 0)) * 100,
        "status": "OPEN" if action == "BUY" else "CLOSED",
    }
    payload["entry_price" if action == "BUY" else "exit_price"] = price
    return await _post_supabase(env, "trades", payload)


async def _persist_history(env, state, market, decision, metadata):
    pair = str(market.get("pair") or state.get("paper_pair") or "btc_idr").upper().replace("_", "/")
    cycle_at = metadata.get("created_at") or datetime.now(timezone.utc).isoformat()
    payload = {
        "cycle_at": cycle_at,
        "trading_date": cycle_at[:10],
        "pair": pair,
        "action": str(decision.get("action") or "HOLD").upper(),
        "raw_action": metadata.get("raw_action"),
        "confidence": max(0, min(100, _json_number(decision.get("confidence")) * 100)),
        "price": _json_number(market.get("last")),
        "balance": _json_number(state.get("balance")),
        "portfolio_value": _json_number(state.get("portfolio_value")),
        "daily_pnl": _json_number(state.get("daily_pnl")),
        "total_pnl": _json_number(state.get("total_pnl")),
        "active_positions": int(state.get("active_positions", 0)),
        "positions": list(state.get("positions") or []),
        "agent_votes": metadata.get("votes") or {},
        "market_scores": metadata.get("market_scores") or {},
        "confidence_components": metadata.get("confidence_components") or {},
        "consensus_action": metadata.get("consensus_action"),
        "consensus_score": _json_number(metadata.get("consensus_score")),
        "position_size": _json_number(metadata.get("position_size")),
        "stop_loss": _optional_json_number(metadata.get("stop_loss")),
        "take_profit": _optional_json_number(metadata.get("take_profit")),
        "reasoning": decision.get("reasoning"),
        "engine_source": metadata.get("source"),
        "engine_warning": metadata.get("warning"),
    }
    return await _post_supabase(env, "paper_history", payload)


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    pair = cf_worker._clean_pair(pair)
    begin = await state_api.begin_cycle()
    if not isinstance(begin, dict) or not begin.get("ok"):
        state = (begin.get("state") if isinstance(begin, dict) else None) or await state_api.get_state()
        return {
            "ok": False,
            "reason": begin.get("reason") if isinstance(begin, dict) else "invalid_cycle_lock_response",
            "state": state_response(state) if state_response else state,
        }

    try:
        market = await cf_worker._market_overview({"env": env, "query_string": f"pair={pair}".encode("latin-1")})
        if not market.get("available") or _json_number(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}

        points = list(market.get("points") or [])
        history = _merge_market_history(await state_api.get_paper_market_history(), points)
        await state_api.set_paper_market_history(history)

        ohlcv = []
        for point in history:
            price = _json_number(point.get("price"))
            if price <= 0:
                continue
            ts = _json_number(point.get("timestamp") or point.get("date"))
            stamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts > 0 else datetime.now(timezone.utc).isoformat()
            ohlcv.append({
                "timestamp": stamp,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": _json_number(point.get("amount"), 1),
            })

        symbol = market["pair"].upper().replace("_", "/")
        last = _json_number(market.get("last"))
        public_move = _json_number(market.get("recent_move"))
        window_move = _history_move_percent(history)
        effective_move = window_move if window_move is not None and abs(window_move) > abs(public_move) else public_move

        market_data = {
            "current_price": last,
            "unified_price": last,
            "price": last,
            "high_24h": _json_number(market.get("high")),
            "low_24h": _json_number(market.get("low")),
            "volume_24h": _json_number(market.get("volume")),
            "change_percent_24h": effective_move,
            "short_term_move_percent": effective_move,
            "public_trade_move_percent": public_move,
            "window_move_percent": window_move,
            "timeframe": "trade",
            "ohlcv": ohlcv,
            "recent_trades": points,
            "volatility": None,
            "data_quality_score": 0.85 if len(ohlcv) >= 80 else max(0.45, min(0.80, len(ohlcv) / 100.0)),
            "trading_knowledge_context": "Momentum requires price/structure confirmation; volume is confirmation; support/resistance must be respected; risk controls remain hard boundaries.",
        }

        orchestrator = CloudflareOrchestrator(
            {"min_confidence": EXECUTION_CONFIDENCE_THRESHOLD, "max_position_size": MAX_POSITION_SIZE, "debug_enabled": True},
            env=env,
        )
        result = await orchestrator.analyze(symbol, market_data)
        raw_action = str(result.final_action or "HOLD").upper()
        action = {"STRONG_BUY": "BUY", "STRONG_SELL": "SELL"}.get(raw_action, raw_action)
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        confidence = _json_number(result.final_confidence)
        scores = {k: _json_number(v) for k, v in dict(result.market_scores or {}).items()}
        range_high = _json_number(market.get("high"))
        range_low = _json_number(market.get("low"))
        range_pos = ((last - range_low) / (range_high - range_low) * 100) if range_high > range_low else 50
        directional = (
            0.40 * scores.get("sentiment", 0)
            + 0.25 * scores.get("technical", 0)
            + 0.35 * scores.get("forecast", 0)
        )

        # Only upgrade HOLD when the independent public-market evidence is
        # directional. A flat market remains HOLD by design.
        if action == "HOLD" and abs(effective_move) >= 0.08 and abs(directional) >= AGGRESSIVE_SIGNAL_THRESHOLD:
            action = "BUY" if directional > 0 else "SELL"
            confidence = max(confidence, 0.70)

        gate_passed = action in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD
        if action in {"BUY", "SELL"} and not gate_passed:
            action = "HOLD"
            reasoning = f"Execution gate blocked {raw_action}: confidence {confidence:.1%} below {EXECUTION_CONFIDENCE_THRESHOLD:.0%}."
        else:
            reasoning = result.execution_reason or result.hold_reason or result.summary

        hold_agents = list(getattr(result, "hold_agents", []) or [])
        opposing_agents = list(getattr(result, "opposing_agents", []) or [])
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
            "market_scores": scores,
            "confidence_components": {k: _json_number(v) for k, v in dict(result.confidence_components or {}).items()},
            "position_size": min(MAX_POSITION_SIZE, _json_number(result.position_size)),
            "stop_loss": _optional_json_number(result.stop_loss),
            "take_profit": _optional_json_number(result.take_profit),
            "execution_reason": result.execution_reason,
            "hold_reason": result.hold_reason,
            "summary": result.summary,
            "agents_invoked": list(dict(result.agent_votes or {}).keys()),
            "hold_agents": hold_agents,
            "opposing_agents": opposing_agents,
            "market_history_points": len(ohlcv),
            "public_trade_move_percent": public_move,
            "window_move_percent": window_move,
            "effective_move_percent": effective_move,
            "range_position": range_pos,
            "created_at": result.timestamp.isoformat(),
        }

        await state_api.record_orchestrator(metadata)
        persistence = await _persist_decision(env, symbol, action, confidence, reasoning, result)
        payload = {"decision": action, "confidence": confidence, "symbol": symbol, "price": last, "reasoning": reasoning, "analysis": metadata}
        state = await state_api.record_cycle_payload(payload)
        trade = (state.get("last_decision") or {}).get("trade") if isinstance(state, dict) else None
        trade_persistence = await _persist_trade(env, trade, persistence.get("id")) if trade else {"saved": False, "reason": "no_trade"}
        decision = state.get("last_decision") or {"action": action, "confidence": confidence, "reasoning": reasoning}
        history_persistence = await _persist_history(env, state, market, decision, metadata)

        return {
            "ok": True,
            "action": action,
            "raw_action": raw_action,
            "confidence": confidence,
            "market": market,
            "orchestrator": metadata,
            "persistence": {"decision": persistence, "trade": trade_persistence, "history": history_persistence},
            "state": state_response(state) if state_response else state,
        }
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_error: {exc}")
        return {"ok": False, "reason": "cycle_error", "error": str(exc), "state": state_response(state) if state_response else state}
