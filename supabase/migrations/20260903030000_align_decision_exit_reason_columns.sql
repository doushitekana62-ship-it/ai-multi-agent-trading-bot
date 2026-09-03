-- Keep the decisions ledger aligned with paper_cycle.py.
-- These fields already exist on paper_history and are part of the canonical
-- execution/risk audit contract.
ALTER TABLE public.decisions
  ADD COLUMN IF NOT EXISTS risk_exit_reason text,
  ADD COLUMN IF NOT EXISTS exit_reason text;
