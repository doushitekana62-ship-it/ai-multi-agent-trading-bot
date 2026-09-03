-- Compatibility RPC for the deployed paper cycle.
-- The worker historically posted the observation fields directly to /rpc/upsert_market_observation.
-- PostgREST maps JSON keys to function parameters, so this overload preserves that deployed contract
-- while delegating to the canonical jsonb payload RPC.
create or replace function public.upsert_market_observation(
  cycle_id text,
  minute_bucket timestamptz,
  move_from_previous_pct numeric,
  observed_at timestamptz,
  price numeric,
  pulse_status text,
  session_id text,
  source text,
  symbol text,
  trade_count integer,
  observation_type text
) returns public.market_observations
language plpgsql
security definer
set search_path = public
as $$
begin
  return public.upsert_market_observation(
    jsonb_build_object(
      'cycle_id', cycle_id,
      'minute_bucket', minute_bucket,
      'move_from_previous_pct', move_from_previous_pct,
      'observed_at', observed_at,
      'price', price,
      'pulse_status', pulse_status,
      'session_id', session_id,
      'source', source,
      'symbol', symbol,
      'trade_count', trade_count,
      'observation_type', observation_type
    )
  );
end;
$$;

revoke all on function public.upsert_market_observation(text,timestamptz,numeric,timestamptz,numeric,text,text,text,text,integer,text) from public;
grant execute on function public.upsert_market_observation(text,timestamptz,numeric,timestamptz,numeric,text,text,text,text,integer,text) to anon, authenticated, service_role;
notify pgrst, 'reload schema';
