alter table public.market_observations
  add column if not exists open_price numeric,
  add column if not exists close_price numeric,
  add column if not exists sample_count integer not null default 1,
  add column if not exists price_changed boolean not null default false,
  add column if not exists last_direction text;

update public.market_observations
set open_price = coalesce(open_price, price),
    close_price = coalesce(close_price, price),
    sample_count = greatest(coalesce(sample_count, 1), 1),
    price_changed = coalesce(price_changed, false),
    last_direction = coalesce(last_direction, pulse_status);

create or replace function public.upsert_market_observation(p_payload jsonb)
returns public.market_observations
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.market_observations;
  v_symbol text := upper(coalesce(p_payload->>'symbol',''));
  v_source text := coalesce(p_payload->>'source','');
  v_price numeric;
  v_bucket timestamptz;
  v_open numeric;
  v_changed boolean;
  v_direction text;
begin
  v_price := nullif(p_payload->>'price','')::numeric;
  v_bucket := nullif(p_payload->>'minute_bucket','')::timestamptz;
  if v_symbol not in ('BTC/IDR','ETH/IDR','USDT/IDR','XRP/IDR','DOGE/IDR','SOL/IDR','BEAT/IDR','HYPE/IDR','ADA/IDR','TRX/IDR','SHIB/IDR','PEPE/IDR') then raise exception 'unsupported symbol'; end if;
  if v_source not in ('INDODAX public market data','INDODAX public ticker') then raise exception 'invalid market source'; end if;
  if v_price is null or v_price <= 0 then raise exception 'invalid market price'; end if;
  if v_bucket is null or v_bucket < now() - interval '3 hours' or v_bucket > now() + interval '2 minutes' then raise exception 'invalid observation bucket'; end if;

  select * into v_row from public.market_observations
  where symbol=v_symbol and minute_bucket=v_bucket
  order by observed_at desc limit 1;

  if found then
    v_open := coalesce(v_row.open_price, v_row.price);
    v_changed := coalesce(v_row.price_changed,false) or v_price <> v_row.price;
    v_direction := case
      when v_price > v_open then 'GREEN'
      when v_price < v_open then 'RED'
      when v_changed then coalesce(v_row.last_direction,'GRAY')
      else 'GRAY'
    end;
    update public.market_observations set
      cycle_id=p_payload->>'cycle_id',
      session_id=p_payload->>'session_id',
      observed_at=coalesce(nullif(p_payload->>'observed_at','')::timestamptz,now()),
      price=v_price,
      open_price=v_open,
      close_price=v_price,
      source=v_source,
      observation_type=coalesce(p_payload->>'observation_type','TICKER'),
      trade_count=coalesce(nullif(p_payload->>'trade_count','')::integer,0),
      sample_count=coalesce(v_row.sample_count,1)+1,
      price_changed=v_changed,
      last_direction=v_direction,
      move_from_previous_pct=nullif(p_payload->>'move_from_previous_pct','')::numeric,
      pulse_status=v_direction,
      raw_observation=coalesce(p_payload->'raw_observation','{}'::jsonb),
      created_at=now()
    where id=v_row.id returning * into v_row;
  else
    insert into public.market_observations
      (cycle_id,session_id,symbol,observed_at,minute_bucket,price,open_price,close_price,source,observation_type,trade_count,sample_count,price_changed,last_direction,move_from_previous_pct,pulse_status,raw_observation)
    values
      (p_payload->>'cycle_id',p_payload->>'session_id',v_symbol,coalesce(nullif(p_payload->>'observed_at','')::timestamptz,now()),v_bucket,v_price,v_price,v_price,v_source,coalesce(p_payload->>'observation_type','TICKER'),coalesce(nullif(p_payload->>'trade_count','')::integer,0),1,false,'GRAY',nullif(p_payload->>'move_from_previous_pct','')::numeric,'GRAY',coalesce(p_payload->'raw_observation','{}'::jsonb))
    returning * into v_row;
  end if;
  return v_row;
end;
$$;

revoke all on function public.upsert_market_observation(jsonb) from public;
grant execute on function public.upsert_market_observation(jsonb) to anon, authenticated, service_role;
notify pgrst, 'reload schema';
