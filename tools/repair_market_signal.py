from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match in {path}: {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# 1) Make the worker's market endpoint authoritative for both the dashboard and
# the paper cycle: when the public trade stream is empty/unavailable, the live
# ticker is still a real market observation and must not become an empty signal.
cf_worker = ROOT / "fronted/cf_worker.py"
replace_once(
    cf_worker,
    '''    t = ticker["ticker"]\n    points = _normalize_public_trades(trades)[-1440:]\n    return {''',
    '''    t = ticker["ticker"]\n    trade_points = _normalize_public_trades(trades)[-1440:]\n    last_price = float(t.get("last") or 0)\n    ticker_timestamp = int(time.time())\n    ticker_point = {\n        "tid": f"ticker:{pair}:{ticker_timestamp}:{last_price}",\n        "price": last_price,\n        "timestamp": ticker_timestamp,\n        "amount": 0.0,\n        "type": "ticker",\n        "side": "",\n        "source": "INDODAX public ticker",\n        "observation_type": "TICKER",\n    } if last_price > 0 else None\n    points = [*trade_points, ticker_point] if ticker_point else trade_points\n    return {''',
)
replace_once(
    cf_worker,
    '''        "recent_move": _recent_trade_move(points),\n        "recent_move_label": "INDODAX public trades",\n        "points": points,\n        "source": "INDODAX public market data",\n        "market_data_quality": "TRADE_STREAM_OK" if points else "TICKER_ONLY",''',
    '''        "recent_move": _recent_trade_move(points),\n        "recent_move_label": "INDODAX public observations",\n        "points": points,\n        "source": "INDODAX public market data",\n        "market_data_quality": "TRADE_STREAM_PLUS_TICKER" if trade_points else "TICKER_FALLBACK",''',
)

# 2) Preserve observation type and make a minute segment report movement even
# when price returns to the minute open after moving up/down during the minute.
paper_cycle = ROOT / "fronted/paper_cycle.py"
replace_once(
    paper_cycle,
    '''        out.append({"tid": str(item.get("tid") or item.get("trade_id") or ""), "price": price, "timestamp": ts, "amount": _num(item.get("amount")), "type": side, "side": side, "source": "INDODAX public market data"})''',
    '''        out.append({"tid": str(item.get("tid") or item.get("trade_id") or ""), "price": price, "timestamp": ts, "amount": _num(item.get("amount")), "type": side, "side": side, "source": str(item.get("source") or "INDODAX public market data"), "observation_type": str(item.get("observation_type") or ("TRADE" if item.get("tid") or item.get("trade_id") else "UNKNOWN")).upper()})''',
)
replace_once(
    paper_cycle,
    '''def _pulse(points, anchor):\n    current = int(anchor // 60) * 60\n    buckets = {}\n    for point in points:\n        ts = _trade_ts(point); price = _num(point.get("price"))\n        if ts <= 0 or price <= 0 or ts < current - 29 * 60 or ts > anchor:\n            continue\n        bucket = int(ts // 60) * 60\n        row = buckets.setdefault(bucket, {"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "open": price, "high": price, "low": price, "close": price, "trades": 0})\n        row["high"] = max(row["high"], price); row["low"] = min(row["low"], price); row["close"] = price; row["trades"] += 1\n    segments = []\n    for bucket in range(current - 29 * 60, current + 60, 60):\n        row = buckets.get(bucket)\n        if not row:\n            segments.append({"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "status": "GRAY", "move_pct": None, "trades": 0, "open": None, "close": None})\n            continue\n        move = ((row["close"] - row["open"]) / row["open"]) * 100.0 if row["open"] > 0 else 0.0\n        row["move_pct"] = move; row["status"] = "GREEN" if move > 0 else "RED" if move < 0 else "GRAY"; segments.append(row)\n    populated = [x for x in segments if x.get("trades", 0) > 0 and x.get("open")]\n    if not populated:\n        return segments, "GRAY", "GRAY", None\n    net = ((populated[-1]["close"] - populated[0]["open"]) / populated[0]["open"]) * 100.0\n    overall = "GREEN" if net > 0 else "RED" if net < 0 else "GRAY"\n    return segments, overall, segments[-1].get("status", "GRAY"), net''',
    '''def _pulse(points, anchor):\n    current = int(anchor // 60) * 60\n    buckets = {}\n    for point in points:\n        ts = _trade_ts(point); price = _num(point.get("price"))\n        if ts <= 0 or price <= 0 or ts < current - 29 * 60 or ts > anchor:\n            continue\n        bucket = int(ts // 60) * 60\n        row = buckets.setdefault(bucket, {"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "open": price, "high": price, "low": price, "close": price, "trades": 0, "observations": 0, "changed": False})\n        if row["observations"] > 0 and price != row["close"]:\n            row["changed"] = True\n        row["high"] = max(row["high"], price)\n        row["low"] = min(row["low"], price)\n        row["close"] = price\n        row["trades"] += 1 if str(point.get("observation_type", "TRADE")).upper() == "TRADE" else 0\n        row["observations"] += 1\n    segments = []\n    for bucket in range(current - 29 * 60, current + 60, 60):\n        row = buckets.get(bucket)\n        if not row:\n            segments.append({"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "status": "GRAY", "move_pct": None, "trades": 0, "observations": 0, "changed": False, "open": None, "close": None})\n            continue\n        move = ((row["close"] - row["open"]) / row["open"]) * 100.0 if row["open"] > 0 else 0.0\n        if move > 0:\n            status = "GREEN"\n        elif move < 0:\n            status = "RED"\n        elif row["changed"] and row["high"] > row["open"]:\n            status = "GREEN"\n        elif row["changed"] and row["low"] < row["open"]:\n            status = "RED"\n        else:\n            status = "GRAY"\n        row["move_pct"] = move\n        row["status"] = status\n        segments.append(row)\n    populated = [x for x in segments if x.get("observations", 0) > 0 and x.get("open")]\n    if not populated:\n        return segments, "GRAY", "GRAY", None\n    net = ((populated[-1]["close"] - populated[0]["open"]) / populated[0]["open"]) * 100.0\n    overall = "GREEN" if net > 0 else "RED" if net < 0 else "GRAY"\n    return segments, overall, segments[-1].get("status", "GRAY"), net''',
)

# 3) Persist the exact observation used by the cycle so Supabase can be used
# as an auditable market-data source instead of only storing the final action.
needle = '''        market_data.update({"movement_1m": moves["move_1m_pct"] / 100.0 if moves["move_1m_pct"] is not None else None, "movement_5m": moves["move_5m_pct"] / 100.0 if moves["move_5m_pct"] is not None else None, "movement_15m": moves["move_15m_pct"] / 100.0 if moves["move_15m_pct"] is not None else None, "movement_30m": moves["move_30m_pct"] / 100.0 if moves["move_30m_pct"] is not None else None})\n        result = await CloudflareOrchestrator'''
replacement = '''        market_data.update({"movement_1m": moves["move_1m_pct"] / 100.0 if moves["move_1m_pct"] is not None else None, "movement_5m": moves["move_5m_pct"] / 100.0 if moves["move_5m_pct"] is not None else None, "movement_15m": moves["move_15m_pct"] / 100.0 if moves["move_15m_pct"] is not None else None, "movement_30m": moves["move_30m_pct"] / 100.0 if moves["move_30m_pct"] is not None else None})\n        latest_observation = history[-1] if history else {}\n        previous_observation = history[-2] if len(history) > 1 else None\n        previous_price = _num(previous_observation.get("price")) if previous_observation else None\n        latest_price = _num(latest_observation.get("price"))\n        observation_move = ((latest_price - previous_price) / previous_price) * 100.0 if previous_price and latest_price else None\n        observation_ts = _trade_ts(latest_observation) or datetime.now(timezone.utc).timestamp()\n        observation_payload = {\n            "cycle_id": cycle_id,\n            "session_id": session_id,\n            "symbol": symbol,\n            "observed_at": datetime.fromtimestamp(observation_ts, timezone.utc).isoformat(),\n            "minute_bucket": datetime.fromtimestamp(int(observation_ts // 60) * 60, timezone.utc).isoformat(),\n            "price": latest_price,\n            "source": str(latest_observation.get("source") or "INDODAX public market data"),\n            "observation_type": str(latest_observation.get("observation_type") or "TRADE").upper(),\n            "trade_count": sum(1 for point in history if str(point.get("observation_type", "TRADE")).upper() == "TRADE" and int(_trade_ts(point) // 60) == int(observation_ts // 60)),\n            "move_from_previous_pct": observation_move,\n            "pulse_status": current_pulse,\n            "raw_observation": {"price": latest_price, "timestamp": observation_ts, "source": latest_observation.get("source"), "observation_type": latest_observation.get("observation_type")},\n        }\n        observation_result = await _supabase(env, "market_observations", payload=observation_payload)\n        result = await CloudflareOrchestrator'''
replace_once(paper_cycle, needle, replacement)

# The decision row should say saved once it has been accepted by PostgREST.
replace_once(paper_cycle, '"persistence_status": "pending"', '"persistence_status": "saved"')

print("Market signal repair applied")
