-- V0.2 execution ledger reconciliation.
-- Keeps decision/history rows traceable to the same canonical trade record.
ALTER TABLE public.decisions
  ADD COLUMN IF NOT EXISTS trade_id bigint;

ALTER TABLE public.trades
  ADD COLUMN IF NOT EXISTS exit_decision_id bigint;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'decisions_trade_id_fkey') THEN
    ALTER TABLE public.decisions
      ADD CONSTRAINT decisions_trade_id_fkey
      FOREIGN KEY (trade_id) REFERENCES public.trades(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'trades_exit_decision_id_fkey') THEN
    ALTER TABLE public.trades
      ADD CONSTRAINT trades_exit_decision_id_fkey
      FOREIGN KEY (exit_decision_id) REFERENCES public.decisions(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_trades_open_symbol
  ON public.trades(symbol, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_decisions_trade_id
  ON public.decisions(trade_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_market_observations_symbol_minute ON public.market_observations(symbol, minute_bucket);
