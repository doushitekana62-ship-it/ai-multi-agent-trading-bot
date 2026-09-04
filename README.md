# AI Multi-Agent Trading Bot

Implementasi arsitektur Compound Scalping Indodax dengan FastAPI, Supabase, dan mode `paper`/`live`.

Arsitektur: Dashboard -> FastAPI -> Forecast Agent -> Scalping Library Agent -> Executor Agent -> Trading Gateway -> Indodax (live) atau Paper Gateway (paper). Forecast dan Scalping Library tidak memiliki jalur order.

Paper Trading hanya mengganti eksekusi dan saldo: harga tetap berasal dari market publik Indodax, saldo virtual, fee/slippage simulasi. Lifecycle posisi, TP/SL, risk sizing, gradual compounding, daily loss limit, logging, dan Realtime memakai struktur yang sama.

Backend: `app/main.py`; agents ada di `app/agents/`; gateway ada di `app/trading/`; adapter Indodax ada di `app/indodax/`. Default aman adalah `TRADING_MODE=paper` dan bot per-user nonaktif sampai diaktifkan dari dashboard.

Supabase schema ada di `supabase/migrations/0001_trading_schema.sql` dan sudah diterapkan ke project Supabase. RLS aktif pada semua tabel exposed; `positions` dan `forecast_signals` diaktifkan pada Realtime. Tabel inti: `users_settings`, `allocated_coins`, `positions`, `forecast_signals`, `trade_logs`; pendukung: `trading_accounts`, `market_ticks`.

Frontend statis ada di `frontend/` dan workflow `.github/workflows/pages.yml` men-deploy ke GitHub Pages. `frontend/config.js` menggunakan publishable Supabase key dan membutuhkan URL publik FastAPI untuk operasi dashboard. Private keys tetap server-side.

CI `.github/workflows/ci.yml` menjalankan compile check dan unit tests. Test source: 2 passed.
