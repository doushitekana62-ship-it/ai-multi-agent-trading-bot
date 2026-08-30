"""Canonical guarded paper-trading cycle for the Cloudflare runtime."""
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
# Indodax's public trades endpoint is polled every cycle. Keep enough durable
# points to reconstruct multi-minute candles across scheduler invocations.
PULSE_FETCH_LIMIT = 1440
MARKET_HISTORY_LIMIT = 1440


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
    except (TypeError, ValueError, OverflowError):
        return None


def _trade_timestamp(point):
    value = _json_number(point.get("timestamp") or point.get("date"))
    return value / 1000.0 if value > 1_000_000_000_000 else value


def _latest_trade_timestamp(points):
    values = [_trade_timestamp(p) for p in points or [] if _trade_timestamp(p) > 0]
    return max(values) if values else None


def _build_pulse_segments(points, anchor_ts=None):
    """Build 30 one-minute buckets anchored to the newest exchange trade."""
    anchor = float(anchor_ts or _latest_trade_timestamp(points) or datetime.now(timezone.utc).timestamp())
    current_bucket = int(anchor // 60) * 60
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
    result = []
    for bucket in range(current_bucket - (PULSE_MINUTES - 1) * 60, current_bucket + 60, 60):
        row = buckets.get(bucket)
        if row is None:
            result.append({"timestamp": _iso(bucket), "status": "GRAY", "move_pct": None, "trades": 0, "open": None, "close": None})
            continue
        move = ((row["close"] - row["open"]) / row["open"] * 100.0) if row["open"] > 0 else 0.0
        row["move_pct"] = move
        row["status"] = "GREEN" if move > 0 else "RED" if move < 0 else "GRAY"
        result.append(row)
    return result


def _pulse_summary(segments):
    """Return a stable 30m status plus the exact current-minute status."""
    populated = [s for s in segments or [] if s.get("trades", 0) > 0 and s.get("move_pct") is not None]
    if not populated:
        return "GRAY", "GRAY", None
    first = next((s for s in segments if s.get("open") and s.get("trades", 0) > 0), None)
    last = next((s for s in reversed(segments) if s.get("close") and s.get("trades", 0) > 0), None)
    net_move = ((last["close"] - first["open"]) / first["open"] * 100.0) if first and last and first["open"] > 0 else None
    status = "GREEN" if net_move is not None and net_move > 0 else "RED" if net_move is not None and net_move < 0 else "GRAY"
    current = str((segments[-1] if segments else {}).get("status") or "GRAY")
    return status, current, net_move


def _window_move(points, minutes, anchor_ts=None):
    valid = [p for p in points or [] if _trade_timestamp(p) > 0 and _json_number(p.get("price")) > 0]
    if len(valid) < 2:
        return None
    anchor = float(anchor_ts or _latest_trade_timestamp(valid) or datetime.now(timezone.utc).timestamp())
    cutoff = anchor - minutes * 60
    rows = sorted((p for p in valid if cutoff <= _trade_timestamp(p) <= anchor), key=_trade_timestamp)
    if len(rows) < 2:
        return None
    first = _json_number(rows[0].get("price")); last = _json_number(rows[-1].get("price"))
    return ((last - first) / first) * 100.0 if first > 0 else None


def _build_ohlcv_from_trades(points, anchor_ts=None, lookback_minutes=180):
    """Derive valid 1m candles from the same Indodax trades used by Pulse."""
    valid = [p for p in points or [] if _trade_timestamp(p) > 0 and _json_number(p.get("price")) > 0]
    if not valid:
        return []
    anchor = float(anchor_ts or _latest_trade_timestamp(valid) or datetime.now(timezone.utc).timestamp())
    current_bucket = int(anchor // 60) * 60
    buckets = {}
    for point in valid:
        ts = _trade_timestamp(point)
        if ts < current_bucket - lookback_minutes * 60 or ts > anchor:
            continue
        price = _json_number(point.get("price"))
        amount = max(0.0, _json_number(point.get("amount")))
        bucket = int(ts // 60) * 60
        row = buckets.setdefault(bucket, {"timestamp": bucket * 1000, "open": price, "high": price, "low": price, "close": price, "volume": 0.0, "trades": 0})
        row["high"] = max(row["high"], price)
        row["low"] = min(row["low"], price)
        row["close"] = price
        row["volume"] += amount
        row["trades"] += 1
    return [buckets[k] for k in sorted(buckets)]


def _merge_market_history(previous, current, limit=MARKET_HISTORY_LIMIT):
    merged, seen = [], set()
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
    return {name: (getattr(value, "__dict__", {}) if value is not None else {}) for name, value in names.items()}


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
            market["points"] = extra_trades
        if not market.get("available") or _json_number(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable")
            return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}
        history = _merge_market_history(await state_api.get_paper_market_history(), list(market.get("points") or []))
        await state_api.set_paper_market_history(history)
        symbol = market["pair"].upper().replace("_", "/")
        last = _json_number(market.get("last"))
        anchor_ts = _latest_trade_timestamp(history) or datetime.now(timezone.utc).timestamp()
        pulse_segments = _build_pulse_segments(history, anchor_ts)
        pulse_status, current_pulse_status, pulse_net_move = _pulse_summary(pulse_segments)
        move_1m = _window_move(history, 1, anchor_ts)
        move_5m = _window_move(history, 5, anchor_ts)
        move_15m = _window_move(history, 15, anchor_ts)
        move_30m = _window_move(history, 30, anchor_ts)
        derived_ohlcv = _build_ohlcv_from_trades(history, anchor_ts)
        public_move = _json_number(market.get("recent_move")) if market.get("recent_move") is not None else None
        effective_move = move_30m if move_30m is not None else public_move
        market_data = {
            "current_price": last, "unified_price": last, "price": last,
            "high_24h": _json_number(market.get("high")), "low_24h": _json_number(market.get("low")), "volume_24h": _json_number(market.get("volume")),
            "change_percent_24h": effective_move, "short_term_move_percent": move_1m if move_1m is not None else effective_move,
            "public_trade_move_percent": public_move, "window_move_percent": effective_move,
            "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m,
            "timeframe": "1m", "ohlcv": derived_ohlcv, "recent_trades": history, "pulse_segments": pulse_segments,
            "pulse_status": pulse_status, "current_pulse_status": current_pulse_status, "pulse_net_move_30m_pct": pulse_net_move,
            "volatility": None, "data_quality_score": 0.90 if len(derived_ohlcv) >= 30 else max(0.55, min(0.85, len(derived_ohlcv) / 100.0)), "market_data_timestamp": _iso(anchor_ts),
            "trading_knowledge_context": "Momentum requires price/structure confirmation; volume confirms rather than predicts; candlestick patterns require context; risk controls remain hard boundaries.",
        }
        orchestrator = CloudflareOrchestrator({"min_confidence": EXECUTION_CONFIDENCE_THRESHOLD, "max_position_size": MAX_POSITION_SIZE, "debug_enabled": True}, env=env)
        result = await orchestrator.analyze(symbol, market_data)
        raw_action = str(result.final_action or "HOLD").upper(); action = {"STRONG_BUY": "BUY", "STRONG_SELL": "SELL"}.get(raw_action, raw_action)
        if action not in {"BUY", "SELL", "HOLD"}: action = "HOLD"
        confidence = _json_number(result.final_confidence)
        scores = {k: _json_number(v) for k, v in dict(result.market_scores or {}).items()}
        range_high = _json_number(market.get("high")); range_low = _json_number(market.get("low")); range_pos = ((last - range_low) / (range_high - range_low) * 100) if range_high > range_low else 50
        gate_passed = action in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD
        reasoning = result.execution_reason or result.hold_reason or result.summary
        if action in {"BUY", "SELL"} and not gate_passed:
            action = "HOLD"; reasoning = f"Execution gate blocked candidate: confidence {confidence:.1%} below {EXECUTION_CONFIDENCE_THRESHOLD:.0%}."
        hold_analysis = dict(getattr(result, "hold_analysis", {}) or {})
        library_alerts = list(getattr(result, "library_alerts", []) or [])[:4]
        candle_analysis = dict(getattr(result, "candle_analysis", {}) or {})
        agent_details = _agent_details(result)
        metadata = {
            "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "source": getattr(result, "engine_source", "fastapi_cloud"), "warning": getattr(result, "engine_warning", None), "cycle_status": getattr(result, "cycle_status", "ANALYZED"), "symbol": result.symbol, "action": action, "raw_action": raw_action, "confidence": confidence,
            "execution_gate": {"threshold": EXECUTION_CONFIDENCE_THRESHOLD, "passed": gate_passed, "executed_action": action}, "consensus_action": result.consensus_action, "consensus_score": _json_number(result.consensus_score), "votes": dict(result.agent_votes or {}), "market_scores": scores, "confidence_components": {k: _json_number(v) for k, v in dict(result.confidence_components or {}).items()},
            "position_size": min(MAX_POSITION_SIZE, _json_number(result.position_size)), "stop_loss": _optional_json_number(result.stop_loss), "take_profit": _optional_json_number(result.take_profit), "execution_reason": result.execution_reason, "hold_reason": result.hold_reason, "summary": result.summary, "agents_invoked": list(dict(result.agent_votes or {}).keys()), "hold_agents": list(hold_analysis.get("hold_agents") or getattr(result, "hold_agents", []) or []), "opposing_agents": list(hold_analysis.get("opposing_agents") or getattr(result, "opposing_agents", []) or []), "hold_analysis": hold_analysis, "agent_details": agent_details,
            "market_history_points": len(history), "public_trade_move_percent": public_move, "window_move_percent": effective_move, "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status, "current_pulse_status": current_pulse_status, "pulse_net_move_30m_pct": pulse_net_move, "pulse_segments": pulse_segments, "effective_move_percent": effective_move, "range_position": range_pos,
            "market_timestamp": _iso(anchor_ts), "market_source": "INDODAX public market data", "library_version": getattr(result, "library_version", "unknown"), "library_alerts": library_alerts, "candle_analysis": candle_analysis, "knowledge_topics": list(getattr(result, "knowledge_topics", []) or []),
        }
        decision_payload = {
            "symbol": symbol, "action": action, "confidence": max(0, min(100, confidence * 100)), "reasoning": _reasoning_with_alert_bridge(reasoning, library_alerts), "agent_votes": metadata["votes"], "market_scores": scores, "confidence_components": metadata["confidence_components"], "consensus_action": metadata["consensus_action"], "consensus_score": metadata["consensus_score"], "position_size": metadata["position_size"], "stop_loss": metadata["stop_loss"], "take_profit": metadata["take_profit"], "engine_source": metadata["source"], "engine_warning": metadata["warning"], "cycle_status": metadata["cycle_status"], "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status, "agent_details": agent_details, "hold_analysis": hold_analysis, "execution_gate": metadata["execution_gate"], "market_snapshot": {**market, "points": history, "ohlcv": derived_ohlcv, "pulse_segments": pulse_segments, "pulse_status": pulse_status, "current_pulse_status": current_pulse_status, "pulse_net_move_30m_pct": pulse_net_move}, "persistence_status": "pending", "library_version": metadata["library_version"], "library_alerts": library_alerts, "candle_analysis": candle_analysis, "knowledge_topics": metadata["knowledge_topics"],
        }
        decision_persistence = await _supabase_request(env, "decisions", "POST", payload=decision_payload)
        if not decision_persistence.get("saved"):
            state = await state_api.finish_cycle("decision_persistence_failed")
            return {"ok": False, "reason": "decision_persistence_failed", "persistence": decision_persistence, "state": state_response(state) if state_response else state}
        decision_id = decision_persistence.get("id")
        cycle_at = datetime.now(timezone.utc).isoformat()
        history_payload = {
            "cycle_at": cycle_at, "trading_date": cycle_at[:10], "pair": symbol, "action": action, "raw_action": raw_action, "confidence": confidence * 100, "price": last, "balance": _json_number(pre_state.get("balance")), "portfolio_value": _json_number(pre_state.get("portfolio_value")), "daily_pnl": _json_number(pre_state.get("daily_pnl")), "total_pnl": _json_number(pre_state.get("total_pnl")), "active_positions": int(pre_state.get("active_positions", 0)), "positions": list(pre_state.get("positions") or []), "agent_votes": metadata["votes"], "market_scores": scores, "confidence_components": metadata["confidence_components"], "consensus_action": metadata["consensus_action"], "consensus_score": metadata["consensus_score"], "position_size": metadata["position_size"], "stop_loss": metadata["stop_loss"], "take_profit": metadata["take_profit"], "reasoning": decision_payload["reasoning"], "engine_source": metadata["source"], "engine_warning": metadata["warning"], "cycle_status": metadata["cycle_status"], "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "decision_id": decision_id, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "bid": _optional_json_number(market.get("buy")), "ask": _optional_json_number(market.get("sell")), "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "pulse_status": pulse_status, "pulse_segments": pulse_segments, "agent_details": agent_details, "hold_analysis": hold_analysis, "execution_gate": metadata["execution_gate"], "market_snapshot": decision_payload["market_snapshot"], "persistence_status": "pending", "library_version": metadata["library_version"], "library_alerts": library_alerts, "candle_analysis": candle_analysis, "knowledge_topics": metadata["knowledge_topics"],
        }
        history_persistence = await _supabase_request(env, "paper_history", "POST", payload=history_payload)
        if not history_persistence.get("saved"):
            state = await state_api.finish_cycle("history_persistence_failed")
            return {"ok": False, "reason": "history_persistence_failed", "decision_id": decision_id, "persistence": history_persistence, "state": state_response(state) if state_response else state}
        if decision_id:
            await _supabase_request(env, "decisions", "PATCH", query=f"?id=eq.{decision_id}", payload={"persistence_status": "persisted"})
        history_id = history_persistence.get("id")
        if history_id:
            await _supabase_request(env, "paper_history", "PATCH", query=f"?id=eq.{history_id}", payload={"persistence_status": "persisted"})
        state = await state_api.apply_cycle(action, last, confidence, cycle_id, metadata)
        return {"ok": True, "cycle_id": cycle_id, "cycle_number": cycle_number, "decision_id": decision_id, "history_id": history_id, "action": action, "confidence": confidence, "pulse_status": pulse_status, "current_pulse_status": current_pulse_status, "move_1m_pct": move_1m, "move_5m_pct": move_5m, "move_15m_pct": move_15m, "move_30m_pct": move_30m, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "persistence": {"decision": decision_persistence, "history": history_persistence}, "state": state_response(state) if state_response else state}
    except Exception as exc:
        state = await state_api.finish_cycle(f"cycle_exception:{type(exc).__name__}")
        return {"ok": False, "reason": type(exc).__name__, "state": state_response(state) if state_response else state}
