-- Apply this migration to the existing Supabase project before starting the engine.
-- It is intentionally additive and safe for existing rows.
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

alter table public.fills enable row level security;
alter table public.market_snapshots enable row level security;
alter table public.strategy_metrics enable row level security;

create policy if not exists fills_own on public.fills for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy if not exists market_snapshots_read on public.market_snapshots for select to authenticated using (true);
create policy if not exists strategy_metrics_own on public.strategy_metrics for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

grant select,insert,update,delete on public.fills, public.market_snapshots, public.strategy_metrics to authenticated;
create index if not exists idx_orders_exchange_order_id on public.orders (exchange_order_id);
create index if not exists idx_fills_order_executed_at on public.fills (order_id, executed_at desc);
create index if not exists idx_market_snapshots_symbol_captured_at on public.market_snapshots (symbol, captured_at desc);
create index if not exists idx_strategy_metrics_user_window on public.strategy_metrics (user_id, window_end desc);
