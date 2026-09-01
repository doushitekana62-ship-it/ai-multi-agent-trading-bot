-- Paper execution/accounting audit consistency.
-- A paper decision is persisted first, then the authoritative Durable Object
-- ledger executes the action. These fields let the persisted audit row be
-- reconciled with the post-execution ledger state.
alter table public.paper_history
  add column if not exists execution_result jsonb not null default '{}'::jsonb,
  add column if not exists realized_pnl numeric not null default 0,
  add column if not exists unrealized_pnl numeric not null default 0,
  add column if not exists fees numeric not null default 0;

alter table public.decisions
  add column if not exists execution_result jsonb not null default '{}''::jsonb';

create index if not exists paper_history_execution_status_idx
  on public.paper_history(execution_status, cycle_at desc);
