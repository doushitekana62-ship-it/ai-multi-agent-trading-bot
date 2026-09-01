-- Forensic marker for the pre-V0.2 trial row that closed in the Durable Object
-- without a corresponding trade-ledger close event. No rows are deleted.
ALTER TABLE public.trades
  ADD COLUMN IF NOT EXISTS reconciled boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS reconciliation_reason text,
  ADD COLUMN IF NOT EXISTS reconciled_at timestamptz;

UPDATE public.trades t
SET decision_id = 787,
    exit_decision_id = 830,
    exit_price = 1390540000,
    price = 1390540000,
    pnl = -3359.3099904173296,
    status = 'CLOSED',
    closed_at = '2026-09-01 07:57:13.622+00'::timestamptz,
    reconciled = true,
    reconciliation_reason = 'LEGACY_STATE_CLOSE_WITHOUT_TRADE_LEDGER',
    reconciled_at = now()
WHERE t.id = 1
  AND t.status = 'OPEN';
