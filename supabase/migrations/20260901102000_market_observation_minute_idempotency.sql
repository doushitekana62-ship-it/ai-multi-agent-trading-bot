-- One authoritative market-pulse observation per symbol/minute.
-- The Worker may sample the live stream every 5 seconds, but persistence is
-- idempotent at the 1-minute segment boundary so the audit table does not
-- become an unbounded duplicate stream.
CREATE UNIQUE INDEX IF NOT EXISTS uq_market_observations_symbol_minute
  ON public.market_observations(symbol, minute_bucket);
