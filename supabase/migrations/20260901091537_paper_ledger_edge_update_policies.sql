-- The deployed edge Worker currently authenticates to PostgREST with the
-- project public key. Keep updates narrowly bounded to recent paper-ledger
-- rows; SELECT/INSERT policies remain separate and real trading is locked.
DROP POLICY IF EXISTS decisions_recent_update ON public.decisions;
CREATE POLICY decisions_recent_update
ON public.decisions
FOR UPDATE TO anon, authenticated
USING (created_at >= now() - interval '1 day')
WITH CHECK (created_at >= now() - interval '1 day');

DROP POLICY IF EXISTS paper_history_recent_update ON public.paper_history;
CREATE POLICY paper_history_recent_update
ON public.paper_history
FOR UPDATE TO anon, authenticated
USING (cycle_at >= now() - interval '1 day')
WITH CHECK (cycle_at >= now() - interval '1 day');

DROP POLICY IF EXISTS trades_open_close_update ON public.trades;
CREATE POLICY trades_open_close_update
ON public.trades
FOR UPDATE TO anon, authenticated
USING (status = 'OPEN' AND created_at >= now() - interval '7 days')
WITH CHECK (status = 'CLOSED' AND exit_price IS NOT NULL AND closed_at IS NOT NULL);
