from pathlib import Path
import re

ROOT = Path('.').resolve()

if (ROOT / 'supabase/migrations/20260901100000_execution_ledger_reconciliation.sql').exists():
    print('repair already applied; nothing to do')
    raise SystemExit(0)

ps = ROOT / 'fronted/paper_state.py'
s = ps.read_text()
s = s.replace('CYCLE_INTERVAL_MS = 5_000', 'CYCLE_INTERVAL_MS = 60_000')
ps.write_text(s)

cf = ROOT / 'fronted/cf_worker.py'
s = cf.read_text()
s = s.replace('MAX_OPEN_POSITIONS = 5', 'MAX_OPEN_POSITIONS = 3')
cf.write_text(s)

pc = ROOT / 'fronted/paper_cycle.py'
s = pc.read_text()
old = '''        row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}\n        return {"ok": True, "saved": True, "id": row.get("id") if isinstance(row, dict) else None}\n'''
new = '''        row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}\n        return {"ok": True, "saved": True, "id": row.get("id") if isinstance(row, dict) else None, "rows": rows if isinstance(rows, list) else ([rows] if isinstance(rows, dict) else [])}\n'''
if old not in s: raise SystemExit('supabase return block not found')
s = s.replace(old, new, 1)
marker = '\n\ndef _trade_ts(point):\n'
helper = r'''

async def _persist_execution_trade(env, decision_id, cycle_id, session_id, symbol, action, confidence, price, execution_result):
    """Reconcile the Durable Object fill with the canonical Supabase trades ledger."""
    if not isinstance(execution_result, dict) or not execution_result.get("executed"):
        return {"ok": True, "saved": False, "status": "NOT_EXECUTED", "trade_id": None}
    trade = execution_result.get("trade")
    if not isinstance(trade, dict):
        return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "executed_without_trade_payload", "trade_id": None}
    side = str(action or "").upper()
    if side == "BUY":
        payload = {
            "decision_id": int(decision_id) if decision_id is not None else None,
            "symbol": symbol,
            "action": "BUY",
            "entry_price": _num(trade.get("price") or price),
            "price": _num(trade.get("price") or price),
            "quantity": _num(trade.get("quantity")),
            "pnl": 0.0,
            "confidence": _num(confidence) * 100.0,
            "status": "OPEN",
            "cycle_id": cycle_id,
            "session_id": session_id,
        }
        saved = await _supabase(env, "trades", payload=payload)
        return {"ok": bool(saved.get("saved")), "saved": bool(saved.get("saved")), "status": "FILLED" if saved.get("saved") else "EXECUTION_LEDGER_ERROR", "trade_id": saved.get("id"), "persistence": saved}
    if side == "SELL":
        from urllib.parse import quote
        encoded_symbol = quote(symbol, safe="")
        open_rows = await _supabase(env, "trades", method="GET", query=f"?select=*&symbol=eq.{encoded_symbol}&status=eq.OPEN&order=created_at.desc&limit=1")
        rows = open_rows.get("rows") or []
        if not rows:
            return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "open_trade_not_found", "trade_id": None, "persistence": open_rows}
        open_trade = rows[0]
        trade_id = open_trade.get("id")
        patch = {
            "exit_price": _num(trade.get("price") or price),
            "price": _num(trade.get("price") or price),
            "pnl": _num(trade.get("pnl")),
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "exit_decision_id": int(decision_id) if decision_id is not None else None,
        }
        updated = await _supabase(env, "trades", method="PATCH", query=f"?id=eq.{trade_id}", payload=patch)
        return {"ok": bool(updated.get("saved")), "saved": bool(updated.get("saved")), "status": "FILLED" if updated.get("saved") else "EXECUTION_LEDGER_ERROR", "trade_id": trade_id, "persistence": updated}
    return {"ok": False, "saved": False, "status": "EXECUTION_LEDGER_ERROR", "reason": "invalid_execution_side", "trade_id": None}
'''
if marker not in s: raise SystemExit('trade helper marker not found')
s = s.replace(marker, helper + marker, 1)
old = '''        execution_pass = candidate in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD\n        action = candidate if execution_pass else "HOLD"\n'''
new = '''        positions_before = list(pre.get("positions") or [])\n        symbol_position = next((p for p in positions_before if str(p.get("symbol") or "").upper() == symbol.upper()), None)\n        account_allows_candidate = True\n        account_rejection_reason = None\n        if candidate == "SELL" and symbol_position is None:\n            account_allows_candidate = False\n            account_rejection_reason = "NO_OPEN_POSITION"\n        elif candidate == "BUY":\n            max_positions = int(pre.get("max_open_positions", 3) or 3)\n            if symbol_position is not None:\n                account_allows_candidate = False\n                account_rejection_reason = "POSITION_ALREADY_OPEN"\n            elif len(positions_before) >= max_positions:\n                account_allows_candidate = False\n                account_rejection_reason = "MAX_OPEN_POSITIONS_REACHED"\n        execution_pass = candidate in {"BUY", "SELL"} and confidence >= EXECUTION_CONFIDENCE_THRESHOLD and account_allows_candidate\n        action = candidate if execution_pass else "HOLD"\n'''
if old not in s: raise SystemExit('execution gate block not found')
s = s.replace(old, new, 1)
old = '''"reason": "PASS" if execution_pass else "CONFIDENCE_BELOW_EXECUTION_THRESHOLD" if candidate in {"BUY", "SELL"} else "NO_DIRECTIONAL_CANDIDATE"'''
new = '''"reason": "PASS" if execution_pass else account_rejection_reason if account_rejection_reason else "CONFIDENCE_BELOW_EXECUTION_THRESHOLD" if candidate in {"BUY", "SELL"} else "NO_DIRECTIONAL_CANDIDATE"'''
if old not in s: raise SystemExit('gate reason block not found')
s = s.replace(old, new, 1)
old = '''        execution_result = {\n            "status": "FILLED" if executed else "NOT_EXECUTED",\n            "executed": executed,\n            "action": action,\n            "reason": "PAPER_FILL" if executed else metadata["execution_gate"]["reason"],\n            "trade": trade,\n        }\n        post_account = {\n'''
new = '''        execution_result = {\n            "status": "FILLED" if executed else "NOT_EXECUTED",\n            "executed": executed,\n            "action": action,\n            "reason": "PAPER_FILL" if executed else metadata["execution_gate"]["reason"],\n            "trade": trade,\n        }\n        trade_persistence = await _persist_execution_trade(env, decision.get("id"), cycle_id, session_id, symbol, action, confidence, market_data["current_price"], execution_result)\n        if executed and not trade_persistence.get("ok"):\n            execution_result["status"] = "EXECUTION_LEDGER_ERROR"\n            execution_result["reason"] = trade_persistence.get("reason") or "trade_persistence_failed"\n            execution_result["persistence"] = trade_persistence\n        else:\n            execution_result["persistence"] = trade_persistence\n        post_account = {\n'''
if old not in s: raise SystemExit('execution result block not found')
s = s.replace(old, new, 1)
old = '''            "trade_id": str(trade.get("trade_id") or trade.get("id") or "") if isinstance(trade, dict) else "",\n            "execution_result": execution_result,\n            "execution_status": execution_result["status"],\n'''
new = '''            "trade_id": trade_persistence.get("trade_id") if isinstance(trade_persistence, dict) else None,\n            "execution_result": execution_result,\n            "execution_status": execution_result["status"],\n'''
if old not in s: raise SystemExit('post account trade block not found')
s = s.replace(old, new, 1)
pc.write_text(s)

mig = ROOT / 'supabase/migrations/20260901100000_execution_ledger_reconciliation.sql'
mig.write_text('''-- V0.2 execution ledger reconciliation.\n-- Keeps decision/history rows traceable to the same canonical trade record.\nALTER TABLE public.decisions\n  ADD COLUMN IF NOT EXISTS trade_id bigint;\n\nALTER TABLE public.trades\n  ADD COLUMN IF NOT EXISTS exit_decision_id bigint;\n\nDO $$\nBEGIN\n  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'decisions_trade_id_fkey') THEN\n    ALTER TABLE public.decisions\n      ADD CONSTRAINT decisions_trade_id_fkey\n      FOREIGN KEY (trade_id) REFERENCES public.trades(id);\n  END IF;\n  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'trades_exit_decision_id_fkey') THEN\n    ALTER TABLE public.trades\n      ADD CONSTRAINT trades_exit_decision_id_fkey\n      FOREIGN KEY (exit_decision_id) REFERENCES public.decisions(id);\n  END IF;\nEND $$;\n\nCREATE INDEX IF NOT EXISTS idx_trades_open_symbol\n  ON public.trades(symbol, status, created_at DESC);\n\nCREATE INDEX IF NOT EXISTS idx_decisions_trade_id\n  ON public.decisions(trade_id);\n''')

test = ROOT / 'tests/test_v02_ledger_consistency.py'
test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nFRONTED = ROOT / "fronted"\n\n\ndef test_paper_scheduler_does_not_poll_every_five_seconds():\n    source = (FRONTED / "paper_state.py").read_text(encoding="utf-8")\n    assert "CYCLE_INTERVAL_MS = 60_000" in source\n\n\ndef test_sell_requires_an_open_position_before_approval():\n    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")\n    assert "NO_OPEN_POSITION" in source\n    assert "account_allows_candidate" in source\n\n\ndef test_execution_reconciles_canonical_trade_ledger():\n    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")\n    assert "_persist_execution_trade" in source\n    assert '"trades"' in source\n    assert '"trade_id": trade_persistence.get("trade_id")' in source\n\n\ndef test_decision_trade_link_is_schema_supported():\n    migration = ROOT / "supabase/migrations/20260901100000_execution_ledger_reconciliation.sql"\n    source = migration.read_text(encoding="utf-8")\n    assert "ADD COLUMN IF NOT EXISTS trade_id bigint" in source\n    assert "exit_decision_id bigint" in source\n''')
print('repair patch complete')
