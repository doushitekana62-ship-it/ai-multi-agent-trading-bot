alter table public.paper_history add column if not exists cycle_status text;
alter table public.paper_history add column if not exists library_version text;
alter table public.paper_history add column if not exists library_alerts jsonb not null default '[]'::jsonb;
alter table public.paper_history add column if not exists candle_analysis jsonb not null default '{}'::jsonb;
alter table public.paper_history add column if not exists knowledge_topics jsonb not null default '[]'::jsonb;

alter table public.decisions add column if not exists cycle_status text;
alter table public.decisions add column if not exists library_version text;
alter table public.decisions add column if not exists library_alerts jsonb not null default '[]'::jsonb;
alter table public.decisions add column if not exists candle_analysis jsonb not null default '{}'::jsonb;
alter table public.decisions add column if not exists knowledge_topics jsonb not null default '[]'::jsonb;

create index if not exists paper_history_cycle_status_idx on public.paper_history(pair, cycle_at desc, cycle_status);
create index if not exists decisions_cycle_status_idx on public.decisions(symbol, created_at desc, cycle_status);
