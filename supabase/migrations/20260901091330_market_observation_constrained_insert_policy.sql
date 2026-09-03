-- Cloudflare edge runtimes may not be able to present a Supabase service-role
-- credential directly. Keep SELECT/UPDATE/DELETE locked down and permit only
-- tightly constrained market-observation inserts from the public-data adapter.
DROP POLICY IF EXISTS market_observations_constrained_insert ON public.market_observations;
CREATE POLICY market_observations_constrained_insert
ON public.market_observations
FOR INSERT
TO anon, authenticated
WITH CHECK (
  source IN ('INDODAX public market data', 'INDODAX public ticker')
  AND symbol IN ('BTC/IDR','ETH/IDR','USDT/IDR','XRP/IDR','DOGE/IDR','SOL/IDR','BEAT/IDR','HYPE/IDR','ADA/IDR','TRX/IDR','SHIB/IDR','PEPE/IDR')
  AND price > 0
  AND observed_at >= now() - interval '15 minutes'
  AND observed_at <= now() + interval '1 minute'
);
