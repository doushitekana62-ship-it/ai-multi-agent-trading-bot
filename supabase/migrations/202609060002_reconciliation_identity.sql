-- Reconciliation identity for Freqtrade trades.
alter table public.positions add column if not exists external_trade_id text;
create unique index if not exists uq_positions_user_external_trade
  on public.positions (user_id, external_trade_id)
  where external_trade_id is not null;
