-- The paper cycle patches these execution/account fields onto decisions after
-- each cycle. Keep the decisions schema aligned with the V0.2 cycle payload.
ALTER TABLE public.decisions
  ADD COLUMN IF NOT EXISTS execution_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS realized_pnl numeric NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unrealized_pnl numeric NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fees numeric NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS execution_status text;
