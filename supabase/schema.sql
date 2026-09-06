-- Compound Scalping application schema.
-- Freqtrade persistence is isolated in the private `freqtrade` schema.
create schema if not exists freqtrade;
revoke all on schema freqtrade from anon, authenticated;
revoke all on all tables in schema freqtrade from anon, authenticated;
revoke all on all sequences in schema freqtrade from anon, authenticated;

create table if not exists public.users_settings (
  id uuid primary key references auth.users(id) on delete cascade,
  risk_per_trade numeric not null default 0.5,
  compounding_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  side text not null,
  entry_price numeric,
  exit_price numeric,
  tp_price numeric,
  sl_price numeric,
  amount numeric,
  pnl numeric,
  status text not null default 'open',
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.signal_decisions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  decision text not null,
  score numeric,
  regime text,
  reason jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.trade_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  position_id uuid references public.positions(id) on delete set null,
  action text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  position_id uuid references public.positions(id) on delete set null,
  client_order_id text,
  exchange_order_id text,
  symbol text not null,
  side text not null,
  order_type text not null,
  status text not null default 'pending',
  price numeric,
  amount numeric,
  filled numeric,
  average_price numeric,
  fee numeric,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, client_order_id)
);

create table if not exists public.risk_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  severity text not null default 'info',
  symbol text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.bot_health (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  mode text not null default 'paper',
  state text not null default 'BOOT',
  websocket_healthy boolean not null default false,
  market_data_healthy boolean not null default false,
  private_stream_healthy boolean not null default false,
  db_healthy boolean not null default false,
  last_cycle_at timestamptz,
  last_error text,
  updated_at timestamptz not null default now(),
  unique (user_id, mode)
);

-- Required indexes for dashboard/risk queries. In particular, position_id is
-- covered for trade-log joins and lookups.
create index if not exists idx_trade_logs_position_id_created_at
  on public.trade_logs (position_id, created_at desc);
create index if not exists idx_positions_user_status_opened_at
  on public.positions (user_id, status, opened_at desc);
create index if not exists idx_orders_user_status_created_at
  on public.orders (user_id, status, created_at desc);
create index if not exists idx_signal_decisions_user_created_at
  on public.signal_decisions (user_id, created_at desc);
create index if not exists idx_risk_events_user_created_at
  on public.risk_events (user_id, created_at desc);
create index if not exists idx_bot_health_user_mode
  on public.bot_health (user_id, mode);

alter table public.users_settings enable row level security;
alter table public.positions enable row level security;
alter table public.signal_decisions enable row level security;
alter table public.trade_logs enable row level security;
alter table public.orders enable row level security;
alter table public.risk_events enable row level security;
alter table public.bot_health enable row level security;

drop policy if exists users_settings_own on public.users_settings;
drop policy if exists positions_own on public.positions;
drop policy if exists signals_own on public.signal_decisions;
drop policy if exists trade_logs_own on public.trade_logs;
drop policy if exists orders_own on public.orders;
drop policy if exists risk_events_own on public.risk_events;
drop policy if exists bot_health_own on public.bot_health;

create policy users_settings_own on public.users_settings for all using (id=auth.uid()) with check (id=auth.uid());
create policy positions_own on public.positions for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy signals_own on public.signal_decisions for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy trade_logs_own on public.trade_logs for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy orders_own on public.orders for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy risk_events_own on public.risk_events for all using (user_id=auth.uid()) with check (user_id=auth.uid());
create policy bot_health_own on public.bot_health for all using (user_id=auth.uid()) with check (user_id=auth.uid());

grant select,insert,update,delete on
  public.users_settings, public.positions, public.signal_decisions,
  public.trade_logs, public.orders, public.risk_events, public.bot_health
  to authenticated;
