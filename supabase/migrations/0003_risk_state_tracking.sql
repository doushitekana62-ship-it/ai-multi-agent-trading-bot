alter table public.trading_accounts add column if not exists daily_start_date date not null default current_date;
alter table public.trading_accounts add column if not exists peak_equity numeric(24,8) not null default 0;
update public.trading_accounts set peak_equity=greatest(peak_equity, initial_balance, cash_balance) where peak_equity=0;
