-- The edge observation writer can legitimately persist recent public observations
-- whose trade timestamp is older than the current request time. The previous policy
-- incorrectly rejected valid observations older than 15 minutes.
DROP POLICY IF EXISTS market_observations_constrained_insert ON public.market_observations;

CREATE POLICY market_observations_constrained_insert
ON public.market_observations
FOR INSERT
TO anon, authenticated
WITH CHECK (
  source IN ('INDODAX public market data', 'INDODAX public ticker')
  AND symbol IN (
    'BTC/IDR','ETH/IDR','USDT/IDR','XRP/IDR','DOGE/IDR','SOL/IDR',
    'BEAT/IDR','HYPE/IDR','ADA/IDR','TRX/IDR','SHIB/IDR','PEPE/IDR'
  )
  AND price > 0
  AND minute_bucket <= now() + interval '1 minute'
  AND minute_bucket >= now() - interval '2 hours'
);
