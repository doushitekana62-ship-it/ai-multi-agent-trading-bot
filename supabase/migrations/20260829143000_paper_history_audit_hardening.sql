alter table public.paper_history add column if not exists cycle_id text;
alter table public.paper_history add column if not exists session_id text;
alter table public.paper_history add column if not exists cycle_number bigint;
alter table public.paper_history add column if not exists decision_id bigint;
alter table public.paper_history add column if not exists trade_id bigint;
alter table public.paper_history add column if not exists market_timestamp timestamptz;
alter table public.paper_history add column if not exists market_source text;
alter table public.paper_history add column if not exists bid numeric;
alter table public.paper_history add column if not exists ask numeric;
alter table public.paper_history add column if not exists move_1m_pct numeric;
alter table public.paper_history add column if not exists move_5m_pct numeric;
alter table public.paper_history add column if not exists move_15m_pct numeric;
alter table public.paper_history add column if not exists move_30m_pct numeric;
alter table public.paper_history add column if not exists pulse_status text;
alter table public.paper_history add column if not exists pulse_segments jsonb not null default '[]'::jsonb;
alter table public.paper_history add column if not exists agent_details jsonb not null default '{}'::jsonb;
alter table public.paper_history add column if not exists hold_analysis jsonb not null default '{}'::jsonb;
alter table public.paper_history add column if not exists execution_gate jsonb not null default '{}'::jsonb;
alter table public.paper_history add column if not exists market_snapshot jsonb not null default '{}'::jsonb;
alter table public.paper_history add column if not exists persistence_status text not null default 'saved';

alter table public.decisions add column if not exists cycle_id text;
alter table public.decisions add column if not exists session_id text;
alter table public.decisions add column if not exists cycle_number bigint;
alter table public.decisions add column if not exists market_timestamp timestamptz;
alter table public.decisions add column if not exists market_source text;
alter table public.decisions add column if not exists move_1m_pct numeric;
alter table public.decisions add column if not exists move_5m_pct numeric;
alter table public.decisions add column if not exists move_15m_pct numeric;
alter table public.decisions add column if not exists move_30m_pct numeric;
alter table public.decisions add column if not exists pulse_status text;
alter table public.decisions add column if not exists agent_details jsonb not null default '{}'::jsonb;
alter table public.decisions add column if not exists hold_analysis jsonb not null default '{}'::jsonb;
alter table public.decisions add column if not exists execution_gate jsonb not null default '{}'::jsonb;
alter table public.decisions add column if not exists market_snapshot jsonb not null default '{}'::jsonb;
alter table public.decisions add column if not exists persistence_status text not null default 'saved';

alter table public.trades add column if not exists cycle_id text;
alter table public.trades add column if not exists session_id text;

create index if not exists paper_history_cycle_id_idx on public.paper_history(cycle_id);
create index if not exists paper_history_session_cycle_idx on public.paper_history(session_id, cycle_number desc);
create index if not exists paper_history_pulse_idx on public.paper_history(pair, cycle_at desc, pulse_status);
create index if not exists decisions_cycle_id_idx on public.decisions(cycle_id);
create index if not exists decisions_session_cycle_idx on public.decisions(session_id, cycle_number desc);

alter table public.paper_history enable row level security;
alter table public.decisions enable row level security;
alter table public.trades enable row level security;

drop policy if exists "backend can insert paper history" on public.paper_history;
drop policy if exists "backend can read paper history" on public.paper_history;
drop policy if exists "backend can insert decisions" on public.decisions;
drop policy if exists "backend can read decisions" on public.decisions;
drop policy if exists "backend can insert trades" on public.trades;
drop policy if exists "backend can read trades" on public.trades;

create policy "backend can insert paper history" on public.paper_history for insert to anon, authenticated with check (true);
create policy "backend can read paper history" on public.paper_history for select to anon, authenticated using (true);
create policy "backend can insert decisions" on public.decisions for insert to anon, authenticated with check (true);
create policy "backend can read decisions" on public.decisions for select to anon, authenticated using (true);
create policy "backend can insert trades" on public.trades for insert to anon, authenticated with check (true);
create policy "backend can read trades" on public.trades for select to anon, authenticated using (true);
