# AI Multi-Agent Trading Bot

Implementasi arsitektur Compound Scalping Indodax dengan FastAPI, Supabase, dan mode `paper`/`live`.

Arsitektur tidak diubah: Dashboard -> FastAPI -> Forecast Agent -> Scalping Library Agent -> Executor Agent -> Trading Gateway -> Indodax (live) atau Paper Gateway (paper). Forecast dan Scalping Library tidak memiliki jalur order.

Paper Trading hanya mengganti eksekusi dan saldo: harga tetap berasal dari market publik Indodax, saldo virtual, fee/slippage simulasi, sedangkan lifecycle posisi, TP/SL, risk sizing, compounding bertahap, daily loss limit, logging, dan Realtime memakai struktur yang sama.

## Backend

`app/main.py` adalah entry point FastAPI. Jalankan `uvicorn app.main:app --host 0.0.0.0 --port 8000` setelah mengisi environment server dari `.env.example`. Default `TRADING_MODE=paper` dan bot per-user default `bot_enabled=false`.

Agent:
- `forecast_agent.py`: SMA, momentum, RSI, ATR dan usulan TP/SL.
- `scalping_library.py`: validasi confidence, risk-per-trade, allocation, daily loss limit dan gradual compounding.
- `executor_agent.py`: satu-satunya komponen yang boleh mengeksekusi gateway.
- `paper_gateway.py`: virtual execution.
- `live_gateway.py`: adapter private Indodax untuk tahap live.

## Supabase

Schema lengkap ada di `supabase/migrations/0001_trading_schema.sql`. Schema sudah diterapkan ke project Supabase dan diverifikasi. Tabel inti: `users_settings`, `allocated_coins`, `positions`, `forecast_signals`, `trade_logs`; tabel pendukung: `trading_accounts` dan `market_ticks`.

RLS aktif pada semua tabel exposed. `positions` dan `forecast_signals` masuk ke `supabase_realtime`. Backend menggunakan server secret; frontend hanya menggunakan publishable key.

## GitHub Pages

`frontend/` adalah dashboard statis. Workflow `.github/workflows/pages.yml` menerbitkannya ke GitHub Pages. `frontend/config.js` berisi URL Supabase + publishable key dan placeholder URL FastAPI publik. Private Supabase/Indodax secrets tidak dimasukkan ke frontend.

## CI

`.github/workflows/ci.yml` menjalankan compile check dan unit test Python pada push/PR. Test lokal saat source dibuat: 2 passed.

## Secrets

`.env` tidak boleh di-commit. Untuk backend gunakan secret GitHub/hosting yang sesuai. Private Indodax credentials sengaja belum diperlukan untuk Paper Trading.
