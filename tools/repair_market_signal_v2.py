from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match in {path}: {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


paper_cycle = ROOT / "fronted/paper_cycle.py"

insert_before = '''async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):'''
observation_helper = '''async def run_market_observation(env, state_api, pair="btc_idr", session_id=None):
    """Observe real market data without invoking the AI decision engine."""
    pair = cf_worker._clean_pair(pair)
    market = await _fetch_market(env, pair)
    if not market.get("available") or _num(market.get("last")) <= 0:
        return {"ok": False, "reason": "market_data_unavailable"}
    points = _normalize_trades(market.get("points"))[-PULSE_FETCH_LIMIT:]
    history = _merge(await state_api.get_paper_market_history(), points)
    await state_api.set_paper_market_history(history)
    anchor = max([_trade_ts(x) for x in history] or [datetime.now(timezone.utc).timestamp()])
    segments, _, current_pulse, _ = _pulse(history, anchor)
    latest = history[-1] if history else {}
    previous = history[-2] if len(history) > 1 else None
    latest_price = _num(latest.get("price"))
    previous_price = _num(previous.get("price")) if previous else None
    observation_move = ((latest_price - previous_price) / previous_price) * 100.0 if previous_price and latest_price else None
    observation_ts = _trade_ts(latest) or datetime.now(timezone.utc).timestamp()
    observation_id = f"OBS-{uuid.uuid4()}"
    payload = {
        "cycle_id": observation_id,
        "session_id": session_id or datetime.now(timezone.utc).isoformat(),
        "symbol": market["pair"].upper().replace("_", "/"),
        "observed_at": datetime.fromtimestamp(observation_ts, timezone.utc).isoformat(),
        "minute_bucket": datetime.fromtimestamp(int(observation_ts // 60) * 60, timezone.utc).isoformat(),
        "price": latest_price,
        "source": str(latest.get("source") or "INDODAX public market data"),
        "observation_type": str(latest.get("observation_type") or "TRADE").upper(),
        "trade_count": sum(1 for point in history if str(point.get("observation_type", "TRADE")).upper() == "TRADE" and int(_trade_ts(point) // 60) == int(observation_ts // 60)),
        "move_from_previous_pct": observation_move,
        "pulse_status": current_pulse,
        "raw_observation": {"price": latest_price, "timestamp": observation_ts, "source": latest.get("source"), "observation_type": latest.get("observation_type"), "pulse_segments": segments[-1:]},
    }
    saved = await _supabase(env, "market_observations", payload=payload)
    return {"ok": True, "observation_id": saved.get("id"), "persistence": saved, "price": latest_price, "current_pulse_status": current_pulse}


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):'''
replace_once(paper_cycle, insert_before, observation_helper)

paper_state = ROOT / "fronted/paper_state.py"
replace_once(
    paper_state,
    'from paper_cycle import run_paper_cycle',
    'from paper_cycle import run_market_observation, run_paper_cycle',
)
replace_once(
    paper_state,
    'CYCLE_INTERVAL_MS = 60_000\nMAX_POSITIONS = 3',
    'CYCLE_INTERVAL_MS = 5_000\nDECISION_INTERVAL_MS = 60_000\nMAX_POSITIONS = 3',
)
replace_once(
    paper_state,
    '''        try:\n            await run_paper_cycle(self.env, self, state.get("paper_pair") or "btc_idr")\n        except Exception as exc:\n            await self.finish_cycle(f"alarm_cycle_error: {exc}")''',
    '''        try:\n            last_cycle_at = state.get("last_cycle_at")\n            decision_due = True\n            if last_cycle_at:\n                try:\n                    last_cycle_ms = datetime.fromisoformat(str(last_cycle_at)).timestamp() * 1000.0\n                    now_ms = datetime.now(timezone.utc).timestamp() * 1000.0\n                    decision_due = (now_ms - last_cycle_ms) >= DECISION_INTERVAL_MS\n                except (TypeError, ValueError):\n                    decision_due = True\n            if decision_due:\n                await run_paper_cycle(self.env, self, state.get("paper_pair") or "btc_idr")\n            else:\n                await run_market_observation(self.env, self, state.get("paper_pair") or "btc_idr", state.get("started_at"))\n        except Exception as exc:\n            # Observation failures must not be misclassified as decision failures.\n            state = await self._get()\n            state["last_error"] = f"market_observation_error: {type(exc).__name__}: {exc}"\n            state["updated_at"] = _now()\n            await self.ctx.storage.put("state", state)''',
)

print("Five-second market observation cadence repair applied")
