# AI Multi-Agent Trading Bot — Indodax

Bot scalping berbasis FastAPI + Supabase + Indodax dengan dua mode eksekusi:

- `paper`: balance virtual, tanpa order nyata.
- `live`: balance dan order nyata melalui Indodax API.

## Prinsip arsitektur

Alur tetap sama:

Dashboard → FastAPI → Forecast Agent → Scalping Library → Executor Agent → Trading Gateway → Indodax / Paper Ledger → Supabase

Hanya Executor Agent yang boleh meminta eksekusi. Perbedaan paper dan live berada pada trading gateway. Semua fitur strategi, validasi sinyal, TP/SL, compounding, daily loss limit, posisi, log, dan dashboard menggunakan alur yang sama.

## Mode Paper Trading

Paper trading bukan strategi yang berbeda. Paper trading adalah mode eksekusi dengan balance virtual. Harga pasar tetap menggunakan data publik Indodax, sedangkan order tidak dikirim ke private trading API.

Paper mode harus mensimulasikan perilaku order/posisi yang digunakan live sejauh yang didukung simulator: open, TP, SL, close manual, fee, slippage/configurable execution assumptions, PnL, balance, compounding, daily loss limit, dan trade logs.

## Struktur

```text
bot-scalping/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth/
│   │   ├── router.py
│   │   └── security.py
│   ├── agents/
│   │   ├── forecast_agent.py
│   │   ├── scalping_library.py
│   │   └── executor_agent.py
│   ├── trading/
│   │   ├── gateway.py
│   │   ├── paper_gateway.py
│   │   └── live_gateway.py
│   ├── indodax/
│   │   ├── client.py
│   │   └── models.py
│   ├── supabase_client.py
│   ├── routers/
│   │   ├── dashboard.py
│   │   ├── coins.py
│   │   ├── positions.py
│   │   └── trading_mode.py
│   └── scheduler.py
├── .env.example
├── .gitignore
└── requirements.txt
```

## Database

Inti tabel tetap `users_settings`, `allocated_coins`, `positions`, `forecast_signals`, dan `trade_logs`. Tambahkan field mode dan ledger paper agar akun paper terpisah secara jelas dari saldo live:

- `users_settings.trading_mode`: `paper` atau `live`
- `paper_balances`: balance virtual per user/asset
- `paper_orders`: order simulasi dan status eksekusinya

RLS tetap wajib. API key live tidak pernah dikirim ke frontend.

## Aturan keamanan

- Default mode adalah `paper`.
- Perubahan `paper` → `live` harus eksplisit dan diawasi.
- Live API key tidak dipakai saat mode paper.
- API key Indodax tidak boleh memiliki permission withdrawal.
- `.env` tidak boleh masuk Git.
- Gunakan paper trading dan validasi sebelum live dengan modal kecil.

## Roadmap

1. Reset fondasi FastAPI + Supabase.
2. Bangun Indodax market-data client read-only.
3. Bangun Forecast Agent.
4. Bangun dashboard realtime.
5. Bangun Scalping Library.
6. Bangun Paper Trading Gateway dan virtual balance.
7. Uji seluruh lifecycle trade dalam paper mode.
8. Tambahkan Live Trading Gateway yang memakai interface gateway yang sama.
9. Aktifkan compounding dan daily loss limit.

Paper dan live harus memakai interface executor yang sama sehingga pergantian mode tidak mengubah logika strategi.
