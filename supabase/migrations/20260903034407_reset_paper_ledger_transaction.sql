create or replace function public.reset_paper_ledger()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  decisions_count bigint;
  history_count bigint;
  trades_count bigint;
  observations_count bigint;
  event_id bigint;
begin
  select count(*) into decisions_count from public.decisions;
  select count(*) into history_count from public.paper_history;
  select count(*) into trades_count from public.trades;
  select count(*) into observations_count from public.market_observations;

  update public.decisions set trade_id = null where trade_id is not null;
  delete from public.trades;
  delete from public.paper_history;
  delete from public.decisions;
  delete from public.market_observations;

  insert into public.paper_integrity_events
    (severity, event_type, details)
  values
    ('INFO', 'PAPER_RESET', jsonb_build_object(
      'decisions_deleted', decisions_count,
      'paper_history_deleted', history_count,
      'trades_deleted', trades_count,
      'market_observations_deleted', observations_count,
      'reset_at', now()
    ))
  returning id into event_id;

  return jsonb_build_object(
    'ok', true,
    'event_id', event_id,
    'decisions_deleted', decisions_count,
    'paper_history_deleted', history_count,
    'trades_deleted', trades_count,
    'market_observations_deleted', observations_count
  );
end;
$$;

revoke all on function public.reset_paper_ledger() from public, anon, authenticated;
grant execute on function public.reset_paper_ledger() to service_role;
