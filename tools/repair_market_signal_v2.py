from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_if_present(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


paper_cycle = ROOT / "fronted/paper_cycle.py"
app = ROOT / "fastapi_cloud_app.py"
dashboard = ROOT / "fronted/src/pages/Dashboard.jsx"
tools = ROOT / "fronted/src/components/DashboardTools.jsx"
history = ROOT / "fronted/src/components/PaperHistoryLibrary.jsx"

bad_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\",\", \":\"))}".strip() if alerts else text\n'
good_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\',\', \':\'))}".strip() if alerts else text\n'
changed = replace_if_present(paper_cycle, bad_reasoning, good_reasoning)

old_catch = '    except Exception as exc:\n        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}") from exc\n'
new_catch = '    except Exception as exc:\n        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}: {exc}") from exc\n'
app_changed = replace_if_present(app, old_catch, new_catch)

replace_if_present(
    dashboard,
    '<DashboardTools market={market} decision={decision} counts={counts} runtimeHours={runtime} cycles={cycles} targets={targets} dailyActual={dailyPnl} decisionHistory={history} positions={positions} />',
    '<DashboardTools enabled={enabled} market={market} decision={decision} counts={counts} runtimeHours={runtime} cycles={cycles} targets={targets} dailyActual={dailyPnl} decisionHistory={history} positions={positions} />',
)

replace_if_present(
    tools,
    'export default function DashboardTools({ market, decision, counts, runtimeHours = 0, cycles = 0, targets, dailyActual = 0, decisionHistory = [], positions = [] }) {',
    'export default function DashboardTools({ enabled = false, market, decision, counts, runtimeHours = 0, cycles = 0, targets, dailyActual = 0, decisionHistory = [], positions = [] }) {',
)

old_chart = "const chart = useMemo(() => { const points = Array.isArray(market?.points) ? market.points.slice(-60) : []; const labels = points.map((p, i) => p.timestamp ? new Date(Number(p.timestamp) * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : String(i + 1)); const prices = points.map((p) => Number(p.price)); const position = positions[0]; const entry = Number(position?.entry_price || 0); const qty = Number(position?.quantity || 0); const pnl = prices.map((p) => entry > 0 && qty > 0 ? (p - entry) * qty : null); const forecastScore = Number(decision?.market_scores?.forecast || 0); const forecast = prices.map((p, i) => p * (1 + forecastScore * .004 * (i + 1))); return { labels, datasets: [{ label: 'Market Price', data: prices, borderColor: '#666', backgroundColor: 'transparent', yAxisID: 'price', tension: .25, pointRadius: points.length === 1 ? 4 : 0 }, { label: 'Position PnL', data: pnl, borderColor: '#16a34a', backgroundColor: 'transparent', yAxisID: 'pnl', tension: .2, pointRadius: 0 }, { label: 'AI Forecast', data: forecast, borderColor: '#2563eb', backgroundColor: 'transparent', yAxisID: 'price', borderDash: [6,4], tension: .25, pointRadius: 0 }] }; }, [market, decision, positions]);"
new_chart = "const chart = useMemo(() => { const points = Array.isArray(market?.points) ? market.points.slice(-60) : []; const prices = points.map((p) => Number(p.price)).filter((p) => Number.isFinite(p) && p > 0); const lastPrice = prices[prices.length - 1] || Number(market?.last || 0); const position = positions[0]; const entry = Number(position?.entry_price || 0); const qty = Number(position?.quantity || 0); const pnl = prices.map((p) => entry > 0 && qty > 0 ? (p - entry) * qty : null); const baseLabels = points.map((p, i) => p.timestamp ? new Date(Number(p.timestamp) * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : String(i + 1)); const returns = prices.slice(1).map((p, i) => prices[i] > 0 ? (p - prices[i]) / prices[i] : 0).filter((v) => Number.isFinite(v)); const vol = returns.length > 2 ? Math.sqrt(returns.reduce((s, r) => s + r * r, 0) / returns.length) : 0; const score = Math.max(-1, Math.min(1, Number(decision?.market_scores?.forecast || 0))); const forwardBars = 12; const step = Math.max(vol, 0.00015); const confidence = Math.max(0, Math.min(1, Number(decision?.confidence || 0))); const horizonMove = Math.min(0.02, Math.max(0.0005, step * Math.sqrt(forwardBars) * Math.max(0.5, confidence))); const directionMove = score * horizonMove; const futureLabels = Array.from({ length: forwardBars }, (_, i) => { const base = points.length && points[points.length - 1]?.timestamp ? Number(points[points.length - 1].timestamp) * 1000 : Date.now(); return new Date(base + (i + 1) * 60000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }); }); const futureForecast = lastPrice > 0 && enabled && decision ? Array.from({ length: forwardBars }, (_, i) => lastPrice * (1 + directionMove * ((i + 1) / forwardBars))) : []; const forecast = enabled && decision && lastPrice > 0 ? [...Array(Math.max(0, prices.length - 1)).fill(null), lastPrice, ...futureForecast] : []; const labels = enabled && decision && futureForecast.length ? [...baseLabels, ...futureLabels] : baseLabels; return { labels, datasets: [{ label: 'Market Price', data: [...prices, ...(futureForecast.length ? Array(futureForecast.length).fill(null) : [])], borderColor: '#666', backgroundColor: 'transparent', yAxisID: 'price', tension: .25, pointRadius: points.length === 1 ? 4 : 0 }, { label: 'Position PnL', data: [...pnl, ...(futureForecast.length ? Array(futureForecast.length).fill(null) : [])], borderColor: '#16a34a', backgroundColor: 'transparent', yAxisID: 'pnl', tension: .2, pointRadius: 0 }, { label: 'AI Forecast', data: forecast, borderColor: '#2563eb', backgroundColor: 'transparent', yAxisID: 'price', borderDash: [6,4], tension: .25, pointRadius: 2, spanGaps: false }] }; }, [enabled, market, decision, positions]);"
replace_if_present(tools, old_chart, new_chart)

old_apply = '        state = await state_api.apply_cycle(action, market_data["current_price"], confidence, cycle_id, metadata)\n        return {"ok": True, "cycle_id": cycle_id, "cycle_number": cycle_number, "decision_id": decision.get("id"), "history_id": history_result.get("id"), "action": action, "candidate_action": candidate, "confidence": confidence, "pulse_status": pulse_status, "current_pulse_status": current_pulse, "move_1m_pct": moves["move_1m_pct"], "move_5m_pct": moves["move_5m_pct"], "move_15m_pct": moves["move_15m_pct"], "move_30m_pct": moves["move_30m_pct"], "agent_details": details, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "execution_gate": metadata["execution_gate"], "state": state_response(state) if state_response else state}'
new_apply = '''        state = await state_api.apply_cycle(action, market_data["current_price"], confidence, cycle_id, metadata)
        last_decision = state.get("last_decision") if isinstance(state, dict) else {}
        executed = bool(last_decision.get("executed")) if isinstance(last_decision, dict) else False
        trade = last_decision.get("trade") if isinstance(last_decision, dict) else None
        execution_result = {
            "status": "FILLED" if executed else "NOT_EXECUTED",
            "executed": executed,
            "action": action,
            "reason": "PAPER_FILL" if executed else metadata["execution_gate"]["reason"],
            "trade": trade,
        }
        trade_persistence = {"saved": False, "id": None}
        if executed and isinstance(trade, dict):
            trade_persistence = await _supabase(env, "trades", payload={
                "symbol": str(trade.get("symbol") or symbol),
                "action": str(trade.get("action") or action),
                "price": _num(trade.get("price")),
                "quantity": _num(trade.get("quantity")),
                "pnl": _num(trade.get("pnl")),
                "confidence": confidence,
                "cycle_id": cycle_id,
                "session_id": session_id,
            })
            if trade_persistence.get("id"):
                execution_result["trade_id"] = trade_persistence.get("id")
        post_account = {
            "balance": _num(state.get("balance")),
            "portfolio_value": _num(state.get("portfolio_value")),
            "daily_pnl": _num(state.get("daily_pnl")),
            "total_pnl": _num(state.get("total_pnl")),
            "active_positions": int(state.get("active_positions", 0)),
            "positions": list(state.get("positions") or []),
            "realized_pnl": _num(last_decision.get("realized_pnl")) if isinstance(last_decision, dict) else 0.0,
            "unrealized_pnl": sum(_num(p.get("unrealized_pnl")) for p in (state.get("positions") or [])),
            "execution_result": execution_result,
            "execution_status": execution_result["status"],
        }
        if trade_persistence.get("id"):
            post_account["trade_id"] = int(trade_persistence["id"])
        if decision.get("id"):
            await _supabase(env, "decisions", method="PATCH", query=f"?id=eq.{decision.get('id')}", payload={
                "balance": post_account["balance"],
                "portfolio_value": post_account["portfolio_value"],
                "daily_pnl": post_account["daily_pnl"],
                "total_pnl": post_account["total_pnl"],
                "active_positions": post_account["active_positions"],
                "positions": post_account["positions"],
                "execution_status": post_account["execution_status"],
                "execution_result": post_account["execution_result"],
            })
        if history_result.get("id"):
            await _supabase(env, "paper_history", method="PATCH", query=f"?id=eq.{history_result.get('id')}", payload=post_account)
        return {"ok": True, "cycle_id": cycle_id, "cycle_number": cycle_number, "decision_id": decision.get("id"), "history_id": history_result.get("id"), "action": action, "candidate_action": candidate, "confidence": confidence, "execution_result": execution_result, "post_account": post_account, "pulse_status": pulse_status, "current_pulse_status": current_pulse, "move_1m_pct": moves["move_1m_pct"], "move_5m_pct": moves["move_5m_pct"], "move_15m_pct": moves["move_15m_pct"], "move_30m_pct": moves["move_30m_pct"], "agent_details": details, "market_timestamp": metadata["market_timestamp"], "market_source": metadata["market_source"], "execution_gate": metadata["execution_gate"], "state": state_response(state) if state_response else state}'''
replace_if_present(paper_cycle, old_apply, new_apply)

old_history = '<Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Hold / Conflict Analysis</Typography><JsonBlock value={row.hold_analysis} /></Grid>'
new_history = '<Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Execution Result</Typography><Stack spacing={.6}><Chip size="small" label={row.execution_status || row.execution_result?.status || (action === "HOLD" ? "NOT_EXECUTED" : "UNKNOWN")} color={String(row.execution_status || row.execution_result?.status || "").toUpperCase() === "FILLED" ? "success" : "default"} /><Typography variant="caption">Trade ID: {row.trade_id || row.execution_result?.trade_id || "—"}</Typography><Typography variant="caption">Candidate: {row.candidate_action || "—"} · Action: {action}</Typography></Stack></Grid><Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Hold / Conflict Analysis</Typography><JsonBlock value={row.hold_analysis} /></Grid>'
replace_if_present(history, old_history, new_history)

print("Fixed _reasoning f-string syntax" if changed else "_reasoning f-string already fixed")
print("Added AI engine exception detail" if app_changed else "AI engine exception detail already enabled")
print("Applied forecast/history/dashboard consistency repairs")
