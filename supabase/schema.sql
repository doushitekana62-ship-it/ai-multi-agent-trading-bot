-- Application tables remain in public and are protected by RLS.
-- Freqtrade creates its own persistence tables automatically at startup in the
-- private `freqtrade` schema using the PostgreSQL search_path configured by the app.
create schema if not exists freqtrade;
revoke all on schema freqtrade from anon, authenticated;
revoke all on all tables in schema freqtrade from anon, authenticated;
revoke all on all sequences in schema freqtrade from anon, authenticated;

create table if not exists public.users_settings (id uuid primary key references auth.users(id) on delete cascade,risk_per_trade numeric not null default 0.5,compounding_enabled boolean not null default true,created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table if not exists public.positions (id uuid primary key default gen_random_uuid(),user_id uuid not null references auth.users(id) on delete cascade,symbol text not null,side text not null,entry_price numeric,exit_price numeric,tp_price numeric,sl_price numeric,amount numeric,pnl numeric,status text not null default 'open',opened_at timestamptz not null default now(),closed_at timestamptz,created_at timestamptz not null default now());
create table if not exists public.signal_decisions (id uuid primary key default gen_random_uuid(),user_id uuid not null references auth.users(id) on delete cascade,symbol text not null,decision text not null,score numeric,regime text,reason jsonb not null default '{}'::jsonb,created_at timestamptz not null default now());
create table if not exists public.trade_logs (id uuid primary key default gen_random_uuid(),user_id uuid not null references auth.users(id) on delete cascade,position_id uuid references public.positions(id) on delete set null,action text not null,detail jsonb not null default '{}'::jsonb,created_at timestamptz not null default now());
create table if not exists public.bot_health (id uuid primary key default gen_random_uuid(),user_id uuid not null references auth.users(id) on delete cascade,state text not null default 'BOOT',data_fresh boolean not null default true,api_latency_ms numeric,heartbeat_at timestamptz not null default now());

do $$ begin
  execute 'alter table public.users_settings enable row level security';
  execute 'alter table public.positions enable row level security';
  execute 'alter table public.signal_decisions enable row level security';
  execute 'alter table public.trade_logs enable row level security';
  execute 'alter table public.bot_health enable row level security';
end $$;

create policy users_settings_own on public.users_settings for all using (id=auth.uid()) with check (id=auth.uid());
create policy positions_own on public.positions for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy signals_own on public.signal_decisions for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy trade_logs_own on public.trade_logs for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy bot_health_own on public.bot_health for all using (user_id=auth.uid()) with check (user_id=auth.uid());

grant select,insert,update,delete on public.users_settings,public.positions,public.signal_decisions,public.trade_logs,public.bot_health to authenticated;
