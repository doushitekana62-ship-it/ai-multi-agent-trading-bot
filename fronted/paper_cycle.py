"""Shared guarded paper-trading cycle runner.

Every cycle uses the public Indodax source, builds a rolling 30-minute
one-minute pulse, obtains the canonical AI decision, then persists an audit
reservation to Supabase before any paper execution. Supabase is the durable
audit authority.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator
from js import fetch
from pyodide.ffi import to_js

EXECUTION_CONFIDENCE_THRESHOLD = 0.75
MAX_POSITION_SIZE = 0.10
LIBRARY_ALERT_MARKER = "LIBRARY_ALERTS_JSON="
PULSE_MINUTES = 30
PULSE_FETCH_LIMIT = 240


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


def _supabase(env):
    return str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/"), str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()


async def _supabase_request(env, table, method="GET", query="", payload=None):
    url, key = _supabase(env)
    if not url or not key:
        return {"ok": False, "saved": False, "reason": "supabase_credentials_missing"}
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json", "Prefer": "return=representation"}
        options = {"method": method, "headers": headers}
        if payload is not None:
            options["body"] = json.dumps(payload, separators=(",", ":"))
        response = await fetch(f"{url}/rest/v1/{table}{query}", to_js(options))
        status = int(response.status)
        text = await response.text()
        if status < 200 or status >= 300:
            return {"ok": False, "saved": False, "reason": f"supabase_http_{status}", "detail": text[:800]}
        try:
            rows = json.loads(text) if text else []
        except Exception:
            rows = []
        row = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
        return {"ok": True, "saved": True, "id": row.get("id") if isinstance(row, dict) else None, "row": row}
    except Exception as exc:
        return {"ok": False, "saved": False, "reason": type(exc).__name__}


def _iso(value):
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _trade_timestamp(point):
    value = _json_number(point.get("timestamp") or point.get("date"))
    return value / 1000.0 if value > 1_000_000_000_000 else value


def _build_pulse_segments(points, now_ts=None):
    """Return exactly 30 aligned one-minute segments when trade data exists."""
    now_ts = float(now_ts or datetime.now(timezone.utc).timestamp())
    current_bucket = int(now_ts // 60) * 60
    buckets = {}
    for point in points or []:
        ts = _trade_timestamp(point)
        price = _json_number(point.get("price"))
        if ts <= 0 or price <= 0:
            continue
        bucket = int(ts // 60) * 60
        if bucket < current_bucket - (PULSE_MINUTES - 1) * 60 or bucket > current_bucket:
            continue
        row = buckets.setdefault(bucket, {"timestamp": _iso(bucket), "open": price, "high": price, "low": price, "close": price, "trades": 0})
        row["high"] = max(row["high"], price)
        row["low"] = min(row["low"], price)
        row["close"] = price
        row["trades"] += 1
    segments = []
    for bucket in range(current_bucket - (PULSE_MINUTES - 1) * 60, current_bucket + 60, 60):
        row = buckets.get(bucket)
        if not row:
            segments.append({"timestamp": _iso(bucket), "status": "GRAY", "move_pct": None, "trades": 0, "open": None, "close": None})
            continue
        move = ((row["close"] - row["open"]) / row["open"] * 100.0) if row["open"] > 0 else 0.0
        status = "GREEN" if move > 0 else "RED" if move < 0 else "GRAY"
        row.update({"status": status, "move_pct": move})
        segments.append(row)
    return segments


def _window_move(points, minutes):
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - minutes * 60
    rows = sorted((p for p in points or [] if _trade_timestamp(p) >= cutoff and _json_number(p.get("price")) > 0), key=_trade_timestamp)
    if len(rows) < 2:
        return None
    first = _json_number(rows[0].get("price")); last = _json_number(rows[-1].get("price"))
    return ((last - first) / first) * 100.0 if first > 0 else None


def _merge_market_history(previous, current, limit=240):
    merged = []
    seen = set()
    for point in list(previous or []) + list(current or []):
        key = (str(point.get("timestamp") or point.get("date") or ""), str(point.get("price") or ""), str(point.get("amount") or ""), str(point.get("type") or point.get("side") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(point)
    merged.sort(key=_trade_timestamp)
    return merged[-limit:]


def _reasoning_with_alert_bridge(reasoning, alerts):
    clean = str(reasoning or "").split(LIBRARY_ALERT_MARKER, 1)[0].strip()
    if not alerts:
        return clean
    encoded = json.dumps(alerts[:4], separators=(",", ":"), ensure_ascii=True)
    return f"{clean} {LIBRARY_ALERT_MARKER}{encoded}".strip()


async def _fetch_public_trades(pair):
    try:
        payload = await cf_worker._public_indodax(f"/{pair}/trades")
        rows = payload.get("trades", []) if isinstance(payload, dict) else []
        return rows[-PULSE_FETCH_LIMIT:] if isinstance(rows, list) else []
    except Exception:
        return []


def _agent_details(result):
    names = {"sentiment": getattr(result, "sentiment", None), "technical": getattr(result, "technical", None), "decision": getattr(result, "decision", None), "forecast": getattr(result, "forecast", None), "reflection": getattr(result, "reflection", None), "mimic_trader": getattr(result, "mimic_analysis", None)}
    details = {}
    for name, value in names.items():
        raw = getattr(value, "__dict__", {}) if value is not None else {}
        details[name] = raw if isinstance(raw, dict) else {}
    return details


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    pair = cf_worker._clean_pair(pair)
    begin = await state_api.begin_cycle()
    if not isinstance(begin, dict) or not begin.get("ok"):
        state = (begin.get("state") if isinstance(begin, dict) else None) or await state_api.get_state()
        return {"ok": False, "reason": begin.get("reason") if isinstance(begin, dict) else "invalid_cycle_lock_response", "state": state_response(state) if state_response else state}

    cycle_id = str(uuid.uuid4())
    pre_state = await state_api.get_state()
    session_id = str(pre_state.get("started_at") or datetime.now(timezone.utc).isoformat())
    cycle_number = int(pre_state.get("cycles_today", 0)) + 1

    try:
        market = await cf_worker._market_overview({"env": env, "query_string": f"pair={pair}".encode("latin-1")})
        extra_trades = await _fetch_public_trades(pair)
        if extra_trades:
            market["points"] = extra_trades[-PULSE_FETCH_LIMIT:]
        if not market.get("available") or _json_number(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}

        points = list(market.get("points") or [])
        history = _merge_market_history(await state_api.get_paper_market_history(), points)
        await state_api.set_paper_market_history(history)
        symbol = market["pair"].upper().replace("_", "/")
        last = _json_number(market.get("last"))
        pulse_segments = _build_pulse_segments(history)
        move_1m = _window_move(history, 1); move_5m = _window_move(history, 5); move_15m = _window_move(history, 15); move_30m = _window_move(history, 30)
        current_segment = pulse_segments[-1] if pulse_segments else {"status": "GRAY"}
        pulse_status = str(current_segment.get("status") or "GRAY")
        public_move = _json_number(market.get("recent_move"))
        effective_move = move_30m if move_30m is not None else public_move

        orchestrator = CloudflareOrchestrator({"min_confidence": EXECUTION_CONFIDENCE_THRESHOLD, "max_position_size": MAX_POSITION_SIZE, "debug_enabled": True}, env=env)
        market_data = {
            "current_price": last, "unified_price": last, "price": last,
            "high_24h": _json_number(market.get("high")), "low_24h": _json_number(market.get("low")), "volume_24h": _json_number(market.get("volume")),
            "change_percent_24h": effective_move, "short_term_move_percent": move_1m if move_1m is not None else effective_move,
            "public_trade_move_percent": public_move, "window_move_percent": effective_move,
            "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m,
            "timeframe": "1m", "ohlcv": [], "recent_trades": history[-PULSE_FETCH_LIMIT:], "pulse_segments": pulse_segments,
            "pulse_status": pulse_status, "volatility": None,
            "data_quality_score": 0.90 if len(history) >= 80 else max(0.55, min(0.85, len(history) / 100.0)),
            "trading_knowledge_context": "Momentum requires price/structure confirmation; volume confirms rather than predicts; candlestick patterns require context; risk controls remain hard boundaries.",
        }
        result = await orchestrator.analyze(symbol, market_data)
        raw_action = str(result.final_action or "HOLD").upper()
        action = {"STRONG_BUY": "BUY", "STRONG_SELL": "SELL"}.get(raw_action, raw_action)
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"
        confidence = _json_number(result.final_confidence)
        scores = {k: _json_number(v) for k, v in dict(result.market_scores or {}).items()}
        range_high = _json_number(market.get("high")); range_low = _json_number(market.get("low"))
        range_pos = ((last - range_low) / (range_high - range_low) * 100) if range_high > range_low else 50

        # No secondary directional override is allowed here. The Trader output is
        # authoritative; this layer only applies the deterministic execution gate.
        gate_passed = action in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD
        reasoning = result.execution_reason or result.hold_reason or result.summary
        if action in {"BUY", "SELL"} and not gate_passed:
            action = "HOLD"
            reasoning = f"Execution gate blocked candidate: confidence {confidence:.1%} below {EXECUTION_CONFIDENCE_THRESHOLD:.0%}."

        hold_analysis = dict(getattr(result, "hold_analysis", {}) or {})
        library_alerts = list(getattr(result, "library_alerts", []) or [])[:4]
        candle_analysis = dict(getattr(result, "candle_analysis", {}) or {})
        metadata = {
            "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number,
            "source": getattr(result, "engine_source", "fastapi_cloud"), "warning": getattr(result, "engine_warning", None),
            "cycle_status": getattr(result, "cycle_status", "ANALYZED"), "symbol": result.symbol, "action": action, "raw_action": raw_action, "confidence": confidence,
            "execution_gate": {"threshold": EXECUTION_CONFIDENCE_THRESHOLD, "passed": gate_passed, "executed_action": action},
            "consensus_action": result.consensus_action, "consensus_score": _json_number(result.consensus_score), "votes": dict(result.agent_votes or {}), "market_scores": scores,
            "confidence_components": {k: _json_number(v) for k, v in dict(result.confidence_components or {}).items()},
            "position_size": min(MAX_POSITION_SIZE, _json_number(result.position_size)), "stop_loss": _optional_json_number(result.stop_loss), "take_profit": _optional_json_number(result.take_profit),
            "execution_reason": result.execution_reason, "hold_reason": result.hold_reason, "summary": result.summary,
            "agents_invoked": list(dict(result.agent_votes or {}).keys()), "hold_agents": list(hold_analysis.get("hold_agents") or getattr(result, "hold_agents", []) or []),
            "opposing_agents": list(hold_analysis.get("opposing_agents") or getattr(result, "opposing_agents", []) or []), "hold_analysis": hold_analysis, "agent_details": _agent_details(result),
            "market_history_points": len(history), "public_trade_move_percent": public_move, "window_move_percent": effective_move,
            "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status,
            "pulse_segments": pulse_segments, "effective_move_percent": effective_move, "range_position": range_pos,
            "market_timestamp": market.get("timestamp") or datetime.now(timezone.utc).isoformat(), "market_source": "INDODAX public market data",
            "library_version": getattr(result, "library_version", "unknown"), "library_alerts": library_alerts,
            "candle_analysis": candle_analysis, "knowledge_topics": list(getattr(result, "knowledge_topics", []) or []),
        }

        decision_payload = {
            "symbol": symbol, "action": action, "confidence": max(0, min(100, confidence * 100)), "reasoning": _reasoning_with_alert_bridge(reasoning, library_alerts),
            "agent_votes": metadata["votes"], "market_scores": scores, "confidence_components": metadata["confidence_components"],
            "consensus_action": metadata["consensus_action"], "consensus_score": metadata["consensus_score"], "position_size": metadata["position_size"],
            "stop_loss": metadata["stop_loss"], "take_profit": metadata["take_profit"], "engine_source": metadata["source"], "engine_warning": metadata["warning"],
            "cycle_status": metadata["cycle_status"], "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number,
            "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m,
            "pulse_status": pulse_status, "agent_details": metadata["agent_details"], "hold_analysis": hold_analysis, "execution_gate": metadata["execution_gate"],
            "market_snapshot": {"pair": symbol, "last": last, "bid": market.get("buy"), "ask": market.get("sell"), "high": market.get("high"), "low": market.get("low"), "volume": market.get("volume"), "pulse_segments": pulse_segments},
            "persistence_status": "pending",
        }
        decision_persistence = await _supabase_request(env, "decisions", "POST", payload=decision_payload)
        if not decision_persistence.get("saved"):
            state = await state_api.finish_cycle("decision_persistence_failed")
            return {"ok": False, "reason": "decision_persistence_failed", "persistence": decision_persistence, "state": state_response(state) if state_response else state}
        decision_id = decision_persistence.get("id")

        cycle_at = datetime.now(timezone.utc).isoformat()
        history_payload = {
            "cycle_at": cycle_at, "trading_date": cycle_at[:10], "pair": symbol, "action": action, "raw_action": raw_action, "confidence": confidence * 100,
            "price": last, "balance": _json_number(pre_state.get("balance")), "portfolio_value": _json_number(pre_state.get("portfolio_value")), "daily_pnl": _json_number(pre_state.get("daily_pnl")), "total_pnl": _json_number(pre_state.get("total_pnl")),
            "active_positions": int(pre_state.get("active_positions", 0)), "positions": list(pre_state.get("positions") or []), "agent_votes": metadata["votes"], "market_scores": scores,
            "confidence_components": metadata["confidence_components"], "consensus_action": metadata["consensus_action"], "consensus_score": metadata["consensus_score"], "position_size": metadata["position_size"],
            "stop_loss": metadata["stop_loss"], "take_profit": metadata["take_profit"], "reasoning": decision_payload["reasoning"], "engine_source": metadata["source"], "engine_warning": metadata["warning"],
            "cycle_status": metadata["cycle_status"], "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "decision_id": decision_id,
            "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "bid": _optional_json_number(market.get("buy")), "ask": _optional_json_number(market.get("sell")),
            "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status, "pulse_segments": pulse_segments,
            "agent_details": metadata["agent_details"], "hold_analysis": hold_analysis, "execution_gate": metadata["execution_gate"], "market_snapshot": decision_payload["market_snapshot"], "persistence_status": "pending",
        }
        history_persistence = await _supabase_request(env, "paper_history", "POST", payload=history_payload)
        if not history_persistence.get("saved"):
            await _supabase_request(env, "decisions", "PATCH", f"?id=eq.{decision_id}", {"persistence_status": "failed", "engine_warning": "paper_history_insert_failed"})
            state = await state_api.finish_cycle("paper_history_persistence_failed")
            return {"ok": False, "reason": "paper_history_persistence_failed", "persistence": {"decision": decision_persistence, "history": history_persistence}, "state": state_response(state) if state_response else state}
        history_id = history_persistence.get("id")

        payload = {"decision": action, "confidence": confidence, "symbol": symbol, "price": last, "reasoning": decision_payload["reasoning"], "analysis": metadata}
        state = await state_api.record_cycle_payload(payload)
        trade = (state.get("last_decision") or {}).get("trade") if isinstance(state, dict) else None

        trade_persistence = {"saved": False, "reason": "no_trade"}
        trade_id = None
        if trade:
            trade_payload = {
                "decision_id": decision_id, "symbol": trade.get("symbol"), "action": str(trade.get("action") or "").upper(), "price": _json_number(trade.get("price")),
                "quantity": _json_number(trade.get("quantity")), "pnl": _json_number(trade.get("pnl")), "confidence": _json_number(trade.get("confidence", 0)) * 100,
                "status": "OPEN" if str(trade.get("action") or "").upper() == "BUY" else "CLOSED", "cycle_id": cycle_id, "session_id": session_id,
            }
            if trade_payload["action"] == "BUY": trade_payload["entry_price"] = trade_payload["price"]
            else: trade_payload["exit_price"] = trade_payload["price"]
            trade_persistence = await _supabase_request(env, "trades", "POST", payload=trade_payload)
            trade_id = trade_persistence.get("id")

        final_history = {
            "balance": _json_number(state.get("balance")), "portfolio_value": _json_number(state.get("portfolio_value")), "daily_pnl": _json_number(state.get("daily_pnl")), "total_pnl": _json_number(state.get("total_pnl")),
            "active_positions": int(state.get("active_positions", 0)), "positions": list(state.get("positions") or []), "trade_id": trade_id,
            "persistence_status": "saved" if trade_persistence.get("saved") or not trade else "saved_with_trade_persistence_error",
        }
        await _supabase_request(env, "paper_history", "PATCH", f"?id=eq.{history_id}", final_history)
        await _supabase_request(env, "decisions", "PATCH", f"?id=eq.{decision_id}", {"persistence_status": "saved"})

        return {
            "ok": True, "action": action, "raw_action": raw_action, "confidence": confidence,
            "market": {**market, "pulse_segments": pulse_segments, "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status},
            "orchestrator": metadata,
            "persistence": {"decision": {**decision_persistence, "id": decision_id}, "history": {**history_persistence, "id": history_id}, "trade": trade_persistence},
            "state": state_response(state) if state_response else state,
        }
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_error: {exc}")
        return {"ok": False, "reason": "cycle_error", "error": str(exc), "state": state_response(state) if state_response else state}
