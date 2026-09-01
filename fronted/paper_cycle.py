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
PULSE_MINUTES = 30
PULSE_FETCH_LIMIT = 1440
MARKET_HISTORY_LIMIT = 1440
LIBRARY_ALERT_MARKER = "LIBRARY_ALERTS_JSON="


def _num(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default


def _optional_num(value):
    if value is None: return None
    try: return float(value)
    except (TypeError, ValueError): return None


def _safe(value):
    if value is None or isinstance(value, (str, int, float, bool)): return value
    if isinstance(value, datetime): return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    if hasattr(value, "__dict__"): return _safe(vars(value))
    return str(value)


async def _supabase(env, table, method="POST", query="", payload=None):
    base = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    if not base or not key: return {"ok": False, "saved": False, "reason": "supabase_credentials_missing"}
    try:
        options = {"method": method, "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=representation" if "on_conflict=" in query else "return=representation"}}
        if payload is not None: options["body"] = json.dumps(_safe(payload), separators=(",", ":"))
        response = await fetch(f"{base}/rest/v1/{table}{query}", to_js(options)); text = await response.text(); status = int(response.status)
        if status < 200 or status >= 300: return {"ok": False, "saved": False, "reason": f"supabase_http_{status}", "detail": text[:800]}
        try: rows = json.loads(text) if text else []
        except Exception: rows = []
        row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}
        return {"ok": True, "saved": True, "id": row.get("id") if isinstance(row, dict) else None, "rows": rows if isinstance(rows, list) else ([rows] if isinstance(rows, dict) else [])}
    except Exception as exc: return {"ok": False, "saved": False, "reason": f"{type(exc).__name__}: {exc}"}


async def _persist_execution_trade(env, decision_id, cycle_id, session_id, symbol, action, confidence, price, execution_result):
    if not isinstance(execution_result, dict) or not execution_result.get("executed"): return {"ok": True, "saved": False, "status": "NOT_EXECUTED", "trade_id": None}
    trade = execution_result.get("trade")
    if not isinstance(trade, dict): return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "executed_without_trade_payload", "trade_id": None}
    side = str(action or trade.get("action") or "").upper()
    if side == "HOLD": side = str(trade.get("action") or "HOLD").upper()
    if side == "BUY":
        payload = {"decision_id": int(decision_id) if decision_id is not None else None, "symbol": symbol, "action": "BUY", "entry_price": _num(trade.get("price") or price), "price": _num(trade.get("price") or price), "quantity": _num(trade.get("quantity")), "pnl": _num(trade.get("pnl")), "confidence": _num(confidence) * 100.0, "status": "OPEN", "cycle_id": cycle_id, "session_id": session_id}
        saved = await _supabase(env, "trades", payload=payload)
        return {"ok": bool(saved.get("saved")), "saved": bool(saved.get("saved")), "status": "FILLED" if saved.get("saved") else "EXECUTION_LEDGER_ERROR", "trade_id": saved.get("id"), "persistence": saved}
    if side == "SELL":
        from urllib.parse import quote
        encoded_symbol = quote(symbol, safe="")
        open_rows = await _supabase(env, "trades", method="GET", query=f"?select=*&symbol=eq.{encoded_symbol}&status=eq.OPEN&order=created_at.desc&limit=1")
        rows = open_rows.get("rows") or []
        if not rows: return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "open_trade_not_found", "trade_id": None, "persistence": open_rows}
        trade_id = rows[0].get("id")
        patch = {"exit_price": _num(trade.get("price") or price), "price": _num(trade.get("price") or price), "pnl": _num(trade.get("pnl")), "status": "CLOSED", "closed_at": datetime.now(timezone.utc).isoformat(), "exit_decision_id": int(decision_id) if decision_id is not None else None}
        updated = await _supabase(env, "trades", method="PATCH", query=f"?id=eq.{trade_id}", payload=patch)
        return {"ok": bool(updated.get("saved")), "saved": bool(updated.get("saved")), "status": "FILLED" if updated.get("saved") else "EXECUTION_LEDGER_ERROR", "trade_id": trade_id, "persistence": updated}
    return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "invalid_execution_side", "trade_id": None}


def _trade_ts(point):
    value = _num(point.get("timestamp") or point.get("date")); return value / 1000.0 if value > 1_000_000_000_000 else value


def _normalize_trades(payload):
    rows = payload if isinstance(payload, list) else (payload.get("trades") or payload.get("data") or []) if isinstance(payload, dict) else []
    out = []
    for item in rows:
        if not isinstance(item, dict): continue
        price = _num(item.get("price")); ts = _num(item.get("date") or item.get("trade_time") or item.get("timestamp"))
        if price <= 0 or ts <= 0: continue
        side = str(item.get("type") or item.get("side") or "").lower()
        out.append({"tid": str(item.get("tid") or item.get("trade_id") or ""), "price": price, "timestamp": ts, "amount": _num(item.get("amount")), "type": side, "side": side, "source": str(item.get("source") or "INDODAX public market data"), "observation_type": str(item.get("observation_type") or ("TRADE" if item.get("tid") or item.get("trade_id") else "UNKNOWN")).upper()})
    return out


def _merge(previous, current):
    merged, seen = [], set()
    for point in list(previous or []) + list(current or []):
        key = (str(point.get("tid")), str(point.get("timestamp")), str(point.get("price")), str(point.get("amount")), str(point.get("side")))
        if key not in seen: seen.add(key); merged.append(point)
    merged.sort(key=_trade_ts); return merged[-MARKET_HISTORY_LIMIT:]


def _window_move(points, minutes, anchor):
    rows = sorted([p for p in points if _trade_ts(p) > 0 and _num(p.get("price")) > 0 and anchor - minutes * 60 <= _trade_ts(p) <= anchor], key=_trade_ts)
    if len(rows) < 2: return None
    first, last = _num(rows[0]["price"]), _num(rows[-1]["price"]); return ((last - first) / first) * 100.0 if first > 0 else None


def _pulse(points, anchor):
    current = int(anchor // 60) * 60; buckets = {}
    for point in points:
        ts = _trade_ts(point); price = _num(point.get("price"))
        if ts <= 0 or price <= 0 or ts < current - 29 * 60 or ts > anchor: continue
        bucket = int(ts // 60) * 60
        row = buckets.setdefault(bucket, {"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "open": price, "high": price, "low": price, "close": price, "trades": 0, "observations": 0, "changed": False, "last_direction": "GRAY"})
        if row["observations"] > 0 and price != row["close"]: row["changed"] = True; row["last_direction"] = "GREEN" if price > row["close"] else "RED"
        row["high"] = max(row["high"], price); row["low"] = min(row["low"], price); row["close"] = price; row["trades"] += 1 if str(point.get("observation_type", "TRADE")).upper() == "TRADE" else 0; row["observations"] += 1
    segments = []
    for bucket in range(current - 29 * 60, current + 60, 60):
        row = buckets.get(bucket)
        if not row: segments.append({"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "status": "GRAY", "move_pct": None, "trades": 0, "observations": 0, "changed": False, "open": None, "close": None, "last_direction": "GRAY"}); continue
        move = ((row["close"] - row["open"]) / row["open"]) * 100.0 if row["open"] > 0 else 0.0
        row["move_pct"] = move; row["status"] = "GREEN" if move > 0 else "RED" if move < 0 else row.get("last_direction", "GRAY") if row["changed"] else "GRAY"; segments.append(row)
    populated = [x for x in segments if x.get("observations", 0) > 0 and x.get("open")]
    if not populated: return segments, "GRAY", "GRAY", None
    net = ((populated[-1]["close"] - populated[0]["open"]) / populated[0]["open"]) * 100.0; overall = "GREEN" if net > 0 else "RED" if net < 0 else "GRAY"
    return segments, overall, segments[-1].get("status", "GRAY"), net


def _ohlcv(points, anchor):
    current = int(anchor // 60) * 60; buckets = {}
    for point in points:
        ts = _trade_ts(point); price = _num(point.get("price")); amount = max(0.0, _num(point.get("amount")))
        if ts <= 0 or price <= 0 or ts < current - 180 * 60 or ts > anchor: continue
        bucket = int(ts // 60) * 60; row = buckets.setdefault(bucket, {"timestamp": bucket * 1000, "open": price, "high": price, "low": price, "close": price, "volume": 0.0, "trades": 0})
        row["high"] = max(row["high"], price); row["low"] = min(row["low"], price); row["close"] = price; row["volume"] += amount; row["trades"] += 1
    return [buckets[k] for k in sorted(buckets)]


def _agent_details(result):
    names = {"sentiment": getattr(result, "sentiment", None), "technical": getattr(result, "technical", None), "forecast": getattr(result, "forecast", None), "decision": getattr(result, "decision", None), "reflection": getattr(result, "reflection", None), "mimic_trader": getattr(result, "mimic_analysis", None)}; out = {}
    for name, obj in names.items():
        raw = _safe(obj) if obj is not None else {}; raw = raw if isinstance(raw, dict) else {"value": raw}
        out[name] = {"direction": raw.get("direction", "NEUTRAL"), "score": _num(raw.get("score", raw.get("overall_score", raw.get("forecast_score", 0)))), "confidence": _num(raw.get("confidence")), "timeframe": raw.get("timeframe", "1m"), "status": raw.get("status", "UNAVAILABLE" if obj is None else "OK"), "data_timestamp": raw.get("data_timestamp", raw.get("timestamp")), "data_age_seconds": _num(raw.get("data_age_seconds")), "summary": raw.get("summary", ""), "evidence": raw.get("evidence") or raw.get("reasoning") or [], "recommendations": raw.get("recommendations") or [], "warnings": raw.get("warnings") or [], "raw": raw}
    return out


def _reasoning(reason, alerts):
    text = str(reason or "").split(LIBRARY_ALERT_MARKER, 1)[0].strip(); return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(',', ':'))}".strip() if alerts else text


async def _fetch_market(env, pair):
    return await cf_worker._market_overview({"env": env, "query_string": f"pair={pair}".encode("latin-1")})


async def run_market_observation(env, state_api, pair="btc_idr", session_id=None):
    pair = cf_worker._clean_pair(pair); market = await _fetch_market(env, pair)
    if not market.get("available") or _num(market.get("last")) <= 0: return {"ok": False, "reason": "market_data_unavailable"}
    points = _normalize_trades(market.get("points"))[-PULSE_FETCH_LIMIT:]; history = _merge(await state_api.get_paper_market_history(), points); await state_api.set_paper_market_history(history)
    anchor = max([_trade_ts(x) for x in history] or [datetime.now(timezone.utc).timestamp()]); segments, _, current_pulse, _ = _pulse(history, anchor); latest = history[-1] if history else {}; previous = history[-2] if len(history) > 1 else None
    latest_price = _num(latest.get("price")); previous_price = _num(previous.get("price")) if previous else None; observation_move = ((latest_price - previous_price) / previous_price) * 100.0 if previous_price and latest_price else None; observation_ts = _trade_ts(latest) or datetime.now(timezone.utc).timestamp(); observation_id = f"OBS-{uuid.uuid4()}"
    payload = {"cycle_id": observation_id, "session_id": session_id or datetime.now(timezone.utc).isoformat(), "symbol": market["pair"].upper().replace("_", "/"), "observed_at": datetime.fromtimestamp(observation_ts, timezone.utc).isoformat(), "minute_bucket": datetime.fromtimestamp(int(observation_ts // 60) * 60, timezone.utc).isoformat(), "price": latest_price, "source": str(latest.get("source") or "INDODAX public market data"), "observation_type": str(latest.get("observation_type") or "TRADE").upper(), "trade_count": sum(1 for point in history if str(point.get("observation_type", "TRADE")).upper() == "TRADE" and int(_trade_ts(point) // 60) == int(observation_ts // 60)), "move_from_previous_pct": observation_move, "pulse_status": current_pulse, "raw_observation": {"price": latest_price, "timestamp": observation_ts, "source": latest.get("source"), "observation_type": latest.get("observation_type"), "pulse_segments": segments[-1:]}}
    saved = await _supabase(env, "market_observations", query="?on_conflict=symbol,minute_bucket", payload=payload); return {"ok": True, "observation_id": saved.get("id"), "persistence": saved, "price": latest_price, "current_pulse_status": current_pulse}


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    pair = cf_worker._clean_pair(pair); begin = await state_api.begin_cycle()
    if not isinstance(begin, dict) or not begin.get("ok"):
        state = (begin.get("state") if isinstance(begin, dict) else None) or await state_api.get_state(); return {"ok": False, "reason": begin.get("reason") if isinstance(begin, dict) else "cycle_lock_failed", "state": state_response(state) if state_response else state}
    cycle_id = str(uuid.uuid4()); pre = await state_api.get_state(); session_id = str(pre.get("started_at") or datetime.now(timezone.utc).isoformat()); cycle_number = int(pre.get("cycles_today", 0)) + 1
    try:
        market = await _fetch_market(env, pair)
        if not market.get("available") or _num(market.get("last")) <= 0:
            state = await state_api.finish_cycle("market_data_unavailable"); return {"ok": False, "reason": "market_data_unavailable", "state": state_response(state) if state_response else state}
        points = _normalize_trades(market.get("points"))[-PULSE_FETCH_LIMIT:]; history = _merge(await state_api.get_paper_market_history(), points); await state_api.set_paper_market_history(history); anchor = max([_trade_ts(x) for x in history] or [datetime.now(timezone.utc).timestamp()]); segments, pulse_status, current_pulse, pulse_net = _pulse(history, anchor); moves = {f"move_{m}m_pct": _window_move(history, m, anchor) for m in (1, 5, 15, 30)}; candles = _ohlcv(history, anchor); symbol = market["pair"].upper().replace("_", "/")
        market_data = {"symbol": symbol, "current_price": _num(market["last"]), "unified_price": _num(market["last"]), "high_24h": _num(market.get("high")), "low_24h": _num(market.get("low")), "volume_24h": _num(market.get("volume")), "ohlcv": candles, "recent_trades": history, "timeframe": "1m", "timestamp": datetime.fromtimestamp(anchor, timezone.utc).isoformat(), "source": "INDODAX public market data", "market_source": "INDODAX public market data", "pulse_segments": segments, "pulse_status": pulse_status, "current_pulse_status": current_pulse, "pulse_net_move_30m_pct": pulse_net, "data_quality_score": min(1.0, max(0.3, len(candles) / 60.0)), **moves}
        market_data.update({"movement_1m": moves["move_1m_pct"] / 100.0 if moves["move_1m_pct"] is not None else None, "movement_5m": moves["move_5m_pct"] / 100.0 if moves["move_5m_pct"] is not None else None, "movement_15m": moves["move_15m_pct"] / 100.0 if moves["move_15m_pct"] is not None else None, "movement_30m": moves["move_30m_pct"] / 100.0 if moves["move_30m_pct"] is not None else None})
        latest_observation = history[-1] if history else {}; previous_observation = history[-2] if len(history) > 1 else None; previous_price = _num(previous_observation.get("price")) if previous_observation else None; latest_price = _num(latest_observation.get("price")); observation_move = ((latest_price - previous_price) / previous_price) * 100.0 if previous_price and latest_price else None; observation_ts = _trade_ts(latest_observation) or datetime.now(timezone.utc).timestamp()
        observation_payload = {"cycle_id": cycle_id, "session_id": session_id, "symbol": symbol, "observed_at": datetime.fromtimestamp(observation_ts, timezone.utc).isoformat(), "minute_bucket": datetime.fromtimestamp(int(observation_ts // 60) * 60, timezone.utc).isoformat(), "price": latest_price, "source": str(latest_observation.get("source") or "INDODAX public market data"), "observation_type": str(latest_observation.get("observation_type") or "TRADE").upper(), "trade_count": sum(1 for point in history if str(point.get("observation_type", "TRADE")).upper() == "TRADE" and int(_trade_ts(point) // 60) == int(observation_ts // 60)), "move_from_previous_pct": observation_move, "pulse_status": current_pulse, "raw_observation": {"price": latest_price, "timestamp": observation_ts, "source": latest_observation.get("source"), "observation_type": latest_observation.get("observation_type")}}
        await _supabase(env, "market_observations", payload=observation_payload)
        result = await CloudflareOrchestrator({"min_confidence": EXECUTION_CONFIDENCE_THRESHOLD, "max_position_size": MAX_POSITION_SIZE, "debug_enabled": True}, env=env).analyze(symbol, market_data)
        raw_action = str(getattr(result, "final_action", "HOLD") or "HOLD").upper(); candidate = {"STRONG_BUY": "BUY", "STRONG_SELL": "SELL"}.get(raw_action, raw_action); candidate = candidate if candidate in {"BUY", "SELL", "HOLD"} else "HOLD"; confidence = _num(getattr(result, "final_confidence", 0)); positions_before = list(pre.get("positions") or []); symbol_position = next((p for p in positions_before if str(p.get("symbol") or "").upper() == symbol.upper()), None)
        risk_preview = await state_api.preview_risk_exit(symbol, market_data["current_price"]) if hasattr(state_api, "preview_risk_exit") else {"triggered": False}
        risk_exit_override = bool(risk_preview.get("triggered")); risk_exit_reason = risk_preview.get("reason") if risk_exit_override else None
        account_allows_candidate = True; account_rejection_reason = None
        if risk_exit_override:
            candidate = "SELL"
        elif candidate == "SELL" and symbol_position is None:
            account_allows_candidate = False; account_rejection_reason = "NO_OPEN_POSITION"
        elif candidate == "BUY":
            max_positions = int(pre.get("max_open_positions", 3) or 3)
            if symbol_position is not None: account_allows_candidate = False; account_rejection_reason = "POSITION_ALREADY_OPEN"
            elif len(positions_before) >= max_positions: account_allows_candidate = False; account_rejection_reason = "MAX_OPEN_POSITIONS_REACHED"
        execution_pass = risk_exit_override or (candidate in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD and account_allows_candidate); action = candidate if execution_pass else "HOLD"
        details = _agent_details(result); scores = {k: _num(v) for k, v in dict(getattr(result, "market_scores", {}) or {}).items()}; components = {k: _num(v) for k, v in dict(getattr(result, "confidence_components", {}) or {}).items()}; hold_analysis = dict(getattr(result, "hold_analysis", {}) or {})
        metadata = {"cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "symbol": symbol, "action": action, "candidate_action": candidate, "raw_action": raw_action, "confidence": confidence, "source": getattr(result, "engine_source", "deterministic_market_fallback"), "warning": getattr(result, "engine_warning", None), "cycle_status": "RISK_EXIT" if risk_exit_override else getattr(result, "cycle_status", "NO_EDGE" if action == "HOLD" else "ANALYZED"), "votes": dict(getattr(result, "agent_votes", {}) or {}), "market_scores": scores, "confidence_components": components, "execution_gate": {"threshold": EXECUTION_CONFIDENCE_THRESHOLD, "candidate_action": candidate, "passed": execution_pass, "executed_action": action, "reason": "RISK_EXIT" if risk_exit_override else "PASS" if execution_pass else account_rejection_reason if account_rejection_reason else "CONFIDENCE_BELOW_EXECUTION_THRESHOLD" if candidate in {"BUY", "SELL"} else "NO_DIRECTIONAL_CANDIDATE"}, "consensus_action": getattr(result, "consensus_action", candidate), "consensus_score": _num(getattr(result, "consensus_score", 0)), "position_size": min(MAX_POSITION_SIZE, _num(getattr(result, "position_size", 0))), "stop_loss": _optional_num(getattr(result, "stop_loss", None)), "take_profit": _optional_num(getattr(result, "take_profit", None)), "execution_reason": "Protective risk exit: " + str(risk_exit_reason) if risk_exit_override else getattr(result, "execution_reason", None), "hold_reason": getattr(result, "hold_reason", None), "summary": getattr(result, "summary", ""), "hold_analysis": hold_analysis, "agent_details": details, "market_timestamp": datetime.fromtimestamp(anchor, timezone.utc).isoformat(), "market_source": "INDODAX public market data", "move_1m_pct": moves["move_1m_pct"], "move_5m_pct": moves["move_5m_pct"], "move_15m_pct": moves["move_15m_pct"], "move_30m_pct": moves["move_30m_pct"], "pulse_status": pulse_status, "current_pulse_status": current_pulse, "pulse_net_move_30m_pct": pulse_net, "pulse_segments": segments, "market_history_points": len(history), "library_version": getattr(result, "library_version", "unknown"), "library_alerts": list(getattr(result, "library_alerts", []) or [])[:4], "candle_analysis": dict(getattr(result, "candle_analysis", {}) or {}), "knowledge_topics": list(getattr(result, "knowledge_topics", []) or []), "risk_exit_reason": risk_exit_reason}
        snapshot = {**market, "points": history, "ohlcv": candles, "pulse_segments": segments, "pulse_status": pulse_status, "current_pulse_status": current_pulse, "pulse_net_move_30m_pct": pulse_net}; now_iso = datetime.now(timezone.utc).isoformat()
        common = {"cycle_at": now_iso, "trading_date": now_iso[:10], "pair": symbol, "action": action, "raw_action": raw_action, "confidence": confidence * 100, "price": market_data["current_price"], "balance": _num(pre.get("balance")), "portfolio_value": _num(pre.get("portfolio_value")), "daily_pnl": _num(pre.get("daily_pnl")), "total_pnl": _num(pre.get("total_pnl")), "active_positions": int(pre.get("active_positions", 0)), "positions": list(pre.get("positions") or []), "agent_votes": metadata["votes"], "market_scores": scores, "confidence_components": components, "consensus_action": metadata["consensus_action"], "consensus_score": metadata["consensus_score"], "position_size": metadata["position_size"], "stop_loss": metadata["stop_loss"], "take_profit": metadata["take_profit"], "reasoning": _reasoning(metadata["execution_reason"] or metadata["hold_reason"] or metadata["summary"], metadata["library_alerts"]), "engine_source": metadata["source"], "engine_warning": metadata["warning"], "cycle_status": metadata["cycle_status"], "cycle_id": cycle_id, "session_id": session_id, "cycle_number": cycle_number, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "bid": _optional_num(market.get("buy")), "ask": _optional_num(market.get("sell")), "move_1m_pct": moves["move_1m_pct"], "move_5m_pct": moves["move_5m_pct"], "move_15m_pct": moves["move_15m_pct"], "move_30m_pct": moves["move_30m_pct"], "pulse_status": pulse_status, "pulse_segments": segments, "agent_details": details, "hold_analysis": hold_analysis, "execution_gate": metadata["execution_gate"], "market_snapshot": snapshot, "persistence_status": "saved", "library_version": metadata["library_version"], "library_alerts": metadata["library_alerts"], "candle_analysis": metadata["candle_analysis"], "knowledge_topics": metadata["knowledge_topics"], "market_regime": metadata["cycle_status"], "current_pulse_status": current_pulse, "pulse_net_move_30m_pct": pulse_net, "data_quality_status": "OK" if len(candles) >= 10 else "DEGRADED", "candidate_action": candidate, "execution_status": "APPROVED" if execution_pass else "NOT_EXECUTED", "risk_rejection_reason": None if execution_pass else metadata["execution_gate"]["reason"] if candidate in {"BUY", "SELL"} else None, "consecutive_hold_count": 0, "no_edge_count": 1 if metadata["cycle_status"] == "NO_EDGE" else 0, "agent_run_count": len(details), "risk_exit_reason": risk_exit_reason}
        decision = await _supabase(env, "decisions", payload=common)
        if not decision.get("saved"):
            state = await state_api.finish_cycle("decision_persistence_failed"); return {"ok": False, "reason": "decision_persistence_failed", "persistence": decision, "state": state_response(state) if state_response else state}
        common["decision_id"] = decision.get("id"); history_result = await _supabase(env, "paper_history", payload=common)
        if not history_result.get("saved"):
            state = await state_api.finish_cycle("history_persistence_failed"); return {"ok": False, "reason": "history_persistence_failed", "persistence": history_result, "state": state_response(state) if state_response else state}
        state = await state_api.apply_cycle(action, market_data["current_price"], confidence, cycle_id, metadata); last_decision = state.get("last_decision") if isinstance(state, dict) else {}; executed = bool(last_decision.get("executed")) if isinstance(last_decision, dict) else False; trade = last_decision.get("trade") if isinstance(last_decision, dict) else None
        actual_action = str(last_decision.get("action") or action).upper() if isinstance(last_decision, dict) else action
        execution_result = {"status": "FILLED" if executed else "NOT_EXECUTED", "executed": executed, "action": actual_action, "reason": "PROTECTIVE_RISK_EXIT" if risk_exit_override else "PAPER_FILL" if executed else metadata["execution_gate"]["reason"], "trade": trade}
        trade_persistence = await _persist_execution_trade(env, decision.get("id"), cycle_id, session_id, symbol, actual_action, confidence, market_data["current_price"], execution_result); execution_result["persistence"] = trade_persistence
        if executed and not trade_persistence.get("ok"): execution_result["status"] = "EXECUTION_LEDGER_ERROR"; execution_result["reason"] = trade_persistence.get("reason") or "trade_persistence_failed"
        post_account = {"balance": _num(state.get("balance")), "portfolio_value": _num(state.get("portfolio_value")), "daily_pnl": _num(state.get("daily_pnl")), "total_pnl": _num(state.get("total_pnl")), "active_positions": int(state.get("active_positions", 0)), "positions": list(state.get("positions") or []), "realized_pnl": _num(last_decision.get("realized_pnl")) if isinstance(last_decision, dict) else 0.0, "unrealized_pnl": sum(_num(p.get("unrealized_pnl")) for p in (state.get("positions") or [])), "trade_id": trade_persistence.get("trade_id") if isinstance(trade_persistence, dict) else None, "execution_result": execution_result, "execution_status": execution_result["status"], "action": actual_action, "risk_exit_reason": last_decision.get("risk_exit_reason") if isinstance(last_decision, dict) else risk_exit_reason, "fees": _num(last_decision.get("fee")) if isinstance(last_decision, dict) else 0.0}
        if decision.get("id"): await _supabase(env, "decisions", method="PATCH", query=f"?id=eq.{decision.get('id')}", payload=post_account)
        if history_result.get("id"): await _supabase(env, "paper_history", method="PATCH", query=f"?id=eq.{history_result.get('id')}", payload=post_account)
        return {"ok": True, "cycle_id": cycle_id, "cycle_number": cycle_number, "decision_id": decision.get("id"), "history_id": history_result.get("id"), "action": actual_action, "candidate_action": candidate, "confidence": confidence, "execution_result": execution_result, "post_account": post_account, "pulse_status": pulse_status, "current_pulse_status": current_pulse, "move_1m_pct": moves["move_1m_pct"], "move_5m_pct": moves["move_5m_pct"], "move_15m_pct": moves["move_15m_pct"], "move_30m_pct": moves["move_30m_pct"], "agent_details": details, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "execution_gate": metadata["execution_gate"], "risk_exit_reason": risk_exit_reason, "state": state_response(state) if state_response else state}
    except Exception as exc:
        state = await state_api.finish_cycle(f"paper_cycle_error: {type(exc).__name__}: {exc}"); return {"ok": False, "reason": "paper_cycle_error", "error": f"{type(exc).__name__}: {exc}", "state": state_response(state) if state_response else state}
