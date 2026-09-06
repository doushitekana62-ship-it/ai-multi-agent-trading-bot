-- Production migration: apply before enabling the engine.
-- Additive and designed to repair the older schema used by the runtime monitor.

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

-- Repair the old bot_health shape used before the reconciliation work.
alter table public.bot_health add column if not exists mode text default 'paper';
alter table public.bot_health add column if not exists websocket_healthy boolean default false;
alter table public.bot_health add column if not exists market_data_healthy boolean default false;
alter table public.bot_health add column if not exists private_stream_healthy boolean default false;
alter table public.bot_health add column if not exists db_healthy boolean default false;
alter table public.bot_health add column if not exists last_cycle_at timestamptz;
alter table public.bot_health add column if not exists last_error text;
alter table public.bot_health add column if not exists updated_at timestamptz default now();

update public.bot_health set mode = coalesce(mode, 'paper'), updated_at = coalesce(updated_at, now());
delete from public.bot_health a using public.bot_health b
where a.user_id = b.user_id and a.mode = b.mode and a.id < b.id;
create unique index if not exists uq_bot_health_user_mode on public.bot_health (user_id, mode);

create table if not exists public.fills (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  order_id uuid references public.orders(id) on delete set null,
  exchange_trade_id text,
  symbol text not null,
  side text not null,
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

alter table public.orders enable row level security;
alter table public.risk_events enable row level security;
alter table public.fills enable row level security;
alter table public.market_snapshots enable row level security;
alter table public.strategy_metrics enable row level security;
alter table public.bot_health enable row level security;

drop policy if exists orders_own on public.orders;
drop policy if exists risk_events_own on public.risk_events;
drop policy if exists fills_own on public.fills;
drop policy if exists market_snapshots_read on public.market_snapshots;
drop policy if exists strategy_metrics_own on public.strategy_metrics;
drop policy if exists bot_health_own on public.bot_health;
create policy orders_own on public.orders for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy risk_events_own on public.risk_events for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy fills_own on public.fills for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy market_snapshots_read on public.market_snapshots for select to authenticated using (true);
create policy strategy_metrics_own on public.strategy_metrics for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy bot_health_own on public.bot_health for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

grant select,insert,update,delete on public.orders, public.risk_events, public.fills, public.market_snapshots, public.strategy_metrics, public.bot_health to authenticated;
create index if not exists idx_orders_exchange_order_id on public.orders (exchange_order_id);
create index if not exists idx_orders_position_created_at on public.orders (position_id, created_at desc);
create index if not exists idx_risk_events_user_created_at on public.risk_events (user_id, created_at desc);
create index if not exists idx_fills_order_executed_at on public.fills (order_id, executed_at desc);
create index if not exists idx_market_snapshots_symbol_captured_at on public.market_snapshots (symbol, captured_at desc);
create index if not exists idx_strategy_metrics_user_window on public.strategy_metrics (user_id, window_end desc);
