-- Detailed paper-trading observability contract.
ALTER TABLE public.paper_history
  ADD COLUMN IF NOT EXISTS market_regime text,
  ADD COLUMN IF NOT EXISTS current_pulse_status text,
  ADD COLUMN IF NOT EXISTS pulse_net_move_30m_pct numeric,
  ADD COLUMN IF NOT EXISTS data_quality_status text,
  ADD COLUMN IF NOT EXISTS candidate_action text,
  ADD COLUMN IF NOT EXISTS execution_status text,
  ADD COLUMN IF NOT EXISTS risk_rejection_reason text,
  ADD COLUMN IF NOT EXISTS consecutive_hold_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS no_edge_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS agent_run_count integer DEFAULT 0;

ALTER TABLE public.decisions
  ADD COLUMN IF NOT EXISTS market_regime text,
  ADD COLUMN IF NOT EXISTS current_pulse_status text,
  ADD COLUMN IF NOT EXISTS pulse_net_move_30m_pct numeric,
  ADD COLUMN IF NOT EXISTS data_quality_status text,
  ADD COLUMN IF NOT EXISTS candidate_action text,
  ADD COLUMN IF NOT EXISTS execution_status text,
  ADD COLUMN IF NOT EXISTS risk_rejection_reason text,
  ADD COLUMN IF NOT EXISTS consecutive_hold_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS no_edge_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS agent_run_count integer DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_paper_history_cycle_at ON public.paper_history(cycle_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_session_cycle ON public.decisions(session_id, cycle_number DESC);
