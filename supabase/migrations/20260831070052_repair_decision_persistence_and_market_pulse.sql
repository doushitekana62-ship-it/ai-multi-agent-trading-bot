-- Repair migration for the production decision persistence contract.
-- The cycle writer already sends raw_action and pulse_segments and the dashboard
-- already reads both fields. The production decisions table was missing them,
-- causing POST /rest/v1/decisions to return HTTP 400 and the UI to report
-- decision_persistence_failed.

ALTER TABLE public.decisions
  ADD COLUMN IF NOT EXISTS raw_action text,
  ADD COLUMN IF NOT EXISTS pulse_segments jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_decisions_pulse_status
  ON public.decisions(symbol, created_at DESC, pulse_status);
