"""Shared paper-trading cycle runner.

The same implementation is used by HTTP/manual triggers and the Durable
Object alarm. It never submits real exchange orders.
"""
from __future__ import annotations

import cf_worker


async def run_paper_cycle(env, state_api, pair="btc_idr", state_response=None):
    """Run one guarded paper-only cycle against the supplied state API."""
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

        move = float(market.get("recent_move") or 0.0)
        high = float(market.get("high") or 0.0)
        low = float(market.get("low") or 0.0)
        last = float(market.get("last") or 0.0)
        range_position = ((last - low) / (high - low) * 100.0) if high > low else 50.0

        # Validation signal only. The multi-agent Orchestrator is deliberately
        # kept out of this infrastructure repair until the scheduler/state path
        # is proven end-to-end.
        if move >= 0.15 or range_position >= 80.0:
            action = "BUY"
            confidence = min(0.95, 0.60 + max(abs(move), range_position - 70.0) / 100.0)
        elif move <= -0.15 or range_position <= 20.0:
            action = "SELL"
            confidence = min(0.95, 0.60 + max(abs(move), 20.0 - range_position) / 100.0)
        else:
            action, confidence = "HOLD", 0.50

        payload = {
            "decision": action,
            "confidence": confidence,
            "symbol": market["pair"].upper().replace("_", "/"),
            "price": last,
            "reasoning": (
                "Paper validation signal: "
                f"recent_move={move:.4f}%, range_position={range_position:.1f}%."
            ),
        }
        state = await state_api.record_cycle_payload(payload)
        return {
            "ok": True,
            "action": action,
            "confidence": confidence,
            "market": market,
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
