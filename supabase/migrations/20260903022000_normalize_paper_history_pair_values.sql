-- Keep the paper-history pair identifier canonical (e.g. BTC/IDR).
-- Older cycles used btc_idr and were normalized in production by this migration.
update public.paper_history
set pair = upper(replace(pair, '_', '/'))
where pair is not null
  and pair <> upper(replace(pair, '_', '/'));

create or replace function public.normalize_paper_history_pair()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.pair is not null then
    new.pair := upper(replace(new.pair, '_', '/'));
  end if;
  return new;
end;
$$;

drop trigger if exists trg_normalize_paper_history_pair on public.paper_history;
create trigger trg_normalize_paper_history_pair
before insert or update of pair on public.paper_history
for each row execute function public.normalize_paper_history_pair();
