-- Compound Scalping application schema.
-- Freqtrade persistence is isolated in the private `freqtrade` schema.
create schema if not exists freqtrade;
revoke all on schema freqtrade from anon, authenticated;
revoke all on all tables in schema freqtrade from anon, authenticated;
revoke all on all sequences in schema freqtrade from anon, authenticated;

create table if not exists public.users_settings (
  id uuid primary key references auth.users(id) on delete cascade,
  risk_per_trade numeric not null default 0.5 check (risk_per_trade > 0 and risk_per_trade <= 5),
  compounding_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  side text not null check (side in ('long','short')),
  entry_price numeric,
  exit_price numeric,
  tp_price numeric,
  sl_price numeric,
  amount numeric check (amount is null or amount > 0),
  pnl numeric,
  status text not null default 'open' check (status in ('open','closing','closed','cancelled','reconciled')),
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
  side text not null check (side in ('buy','sell')),
  order_type text not null,
  status text not null default 'pending' check (status in ('pending','open','closed','cancelled','rejected','unknown')),
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

create table if not exists public.fills (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  order_id uuid references public.orders(id) on delete set null,
  exchange_trade_id text,
  symbol text not null,
  side text not null check (side in ('buy','sell')),
  price numeric not null,
  amount numeric not null check (amount > 0),
  fee numeric default 0,
  fee_currency text,
  executed_at timestamptz not null,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, exchange_trade_id)
);

create table if not exists public.market_snapshots (
  id bigint generated always as identity primary key,
  symbol text not null,
  timeframe text not null default '1m',
  captured_at timestamptz not null default now(),
  last_price numeric,
  bid numeric,
  ask numeric,
  spread_bps numeric,
  volume numeric,
  orderbook_imbalance numeric,
  data_quality numeric not null default 1 check (data_quality >= 0 and data_quality <= 1),
  raw jsonb not null default '{}'::jsonb
);

create table if not exists public.strategy_metrics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  strategy text not null,
  symbol text,
  window_start timestamptz not null,
  window_end timestamptz not null,
  trades integer not null default 0,
  wins integer not null default 0,
  losses integer not null default 0,
  pnl numeric not null default 0,
  expectancy numeric,
  profit_factor numeric,
  max_drawdown numeric,
  created_at timestamptz not null default now(),
  unique (user_id, strategy, symbol, window_start, window_end)
);

create table if not exists public.risk_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  severity text not null default 'info' check (severity in ('info','warning','critical')),
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

create index if not exists idx_trade_logs_position_id_created_at on public.trade_logs (position_id, created_at desc);
create index if not exists idx_positions_user_status_opened_at on public.positions (user_id, status, opened_at desc);
create index if not exists idx_orders_user_status_created_at on public.orders (user_id, status, created_at desc);
create index if not exists idx_orders_exchange_order_id on public.orders (exchange_order_id);
create index if not exists idx_fills_order_executed_at on public.fills (order_id, executed_at desc);
create index if not exists idx_market_snapshots_symbol_captured_at on public.market_snapshots (symbol, captured_at desc);
create index if not exists idx_signal_decisions_user_created_at on public.signal_decisions (user_id, created_at desc);
create index if not exists idx_risk_events_user_created_at on public.risk_events (user_id, created_at desc);
create index if not exists idx_bot_health_user_mode on public.bot_health (user_id, mode);
create index if not exists idx_strategy_metrics_user_window on public.strategy_metrics (user_id, window_end desc);

alter table public.users_settings enable row level security;
alter table public.positions enable row level security;
alter table public.signal_decisions enable row level security;
alter table public.trade_logs enable row level security;
alter table public.orders enable row level security;
alter table public.fills enable row level security;
alter table public.market_snapshots enable row level security;
alter table public.strategy_metrics enable row level security;
alter table public.risk_events enable row level security;
alter table public.bot_health enable row level security;

-- Market snapshots are server telemetry. They are not writable from the browser.
drop policy if exists market_snapshots_own on public.market_snapshots;
create policy market_snapshots_read on public.market_snapshots for select to authenticated using (true);

-- User-owned application state.
drop policy if exists users_settings_own on public.users_settings;
drop policy if exists positions_own on public.positions;
drop policy if exists signals_own on public.signal_decisions;
drop policy if exists trade_logs_own on public.trade_logs;
drop policy if exists orders_own on public.orders;
drop policy if exists fills_own on public.fills;
drop policy if exists strategy_metrics_own on public.strategy_metrics;
drop policy if exists risk_events_own on public.risk_events;
drop policy if exists bot_health_own on public.bot_health;

create policy users_settings_own on public.users_settings for all to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy positions_own on public.positions for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy signals_own on public.signal_decisions for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy trade_logs_own on public.trade_logs for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy orders_own on public.orders for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy fills_own on public.fills for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy strategy_metrics_own on public.strategy_metrics for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy risk_events_own on public.risk_events for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy bot_health_own on public.bot_health for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

grant select,insert,update,delete on public.users_settings, public.positions, public.signal_decisions, public.trade_logs, public.orders, public.fills, public.market_snapshots, public.strategy_metrics, public.risk_events, public.bot_health to authenticated;
