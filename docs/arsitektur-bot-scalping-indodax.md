# Arsitektur Bot Compound Scalping — Indodax + FastAPI + Supabase

## 1. Konsep utama

Arsitektur asli dipertahankan. Sistem memiliki tiga agent:

```text
Dashboard (Login + Realtime)
        |
        v
Backend FastAPI
  ├── Agent Forecast          -> indikator + usulan TP/SL
  ├── Agent Library Scalping  -> validasi sinyal + compounding
  └── Agent Pelaksana         -> keputusan eksekusi
        |
        v
   Trading Gateway
      /       \
   PAPER      LIVE
     |           |
Virtual Ledger  Indodax API
        \       /
         Supabase
```

Prinsip penting: hanya Agent Pelaksana yang boleh meminta eksekusi. Agent Forecast dan Agent Library Scalping tidak boleh mengirim order ke Indodax.

## 2. Paper Trading = mode, bukan strategi baru

Paper trading harus memiliki seluruh lifecycle dan aturan yang sama dengan live trading. Perbedaannya hanya sumber balance dan tujuan eksekusi:

| Komponen | Paper | Live |
|---|---|---|
| Harga pasar | Data publik Indodax | Data publik Indodax |
| Balance | Virtual | Saldo akun Indodax |
| Entry order | Simulator | Indodax API |
| TP/SL | Simulator | Indodax / executor |
| Close manual | Virtual execution | Real execution |
| Fee | Simulasi sesuai konfigurasi | Fee aktual/konfigurasi live |
| Slippage | Asumsi simulator | Kondisi pasar nyata |
| PnL | Virtual | Realisasi nyata |
| Compounding | Virtual | Real |
| Daily loss limit | Aktif | Aktif |
| Trade log | Sama | Sama |
| Dashboard | Sama | Sama |

Jangan membuat `paper_strategy.py` yang memiliki aturan berbeda. Strategy layer harus satu. Yang berbeda hanya implementation dari `TradingGateway`.

## 3. Trading Gateway

Gunakan interface tunggal:

```text
TradingGateway
├── get_balance()
├── get_open_orders()
├── place_order()
├── cancel_order()
├── get_order()
└── close_position()
```

Implementasi:

```text
PaperTradingGateway -> paper_balances + paper_orders + market data Indodax
LiveTradingGateway  -> Indodax private API
```

Executor Agent hanya mengenal `TradingGateway`, bukan detail paper/live.

Contoh pemilihan mode:

```python
if settings.trading_mode == "paper":
    gateway = PaperTradingGateway(...)
else:
    gateway = LiveTradingGateway(...)
```

Default harus `paper`.

## 4. Paper balance

Paper balance tidak boleh bercampur dengan saldo live.

Contoh:

```text
paper_balances
- user_id
- asset
- available
- locked
- updated_at
```

Saat akun paper dibuat, berikan initial virtual balance dari konfigurasi. Nilainya dapat di-reset melalui fitur administrasi paper trading.

Paper balance harus berubah akibat lifecycle order seperti akun trading normal: available → locked → settled.

## 5. Paper order execution

Simulator menerima order dari Executor Agent dan menggunakan harga market Indodax sebagai referensi. Simulator mencatat:

```text
paper_orders
- id
- user_id
- symbol
- side
- order_type
- requested_price
- executed_price
- quantity
- fee
- slippage
- status
- created_at
- executed_at
```

Simulator harus menghasilkan event yang dapat diproses oleh pipeline posisi yang sama dengan live:

```text
order accepted
    -> filled
    -> position open
    -> TP/SL condition
    -> position closed
    -> PnL calculated
    -> balance settled
    -> trade_logs
```

## 6. Database inti

Tabel asli tetap:

- `users_settings`
- `allocated_coins`
- `positions`
- `forecast_signals`
- `trade_logs`

Tambahan untuk paper mode:

### `users_settings`

Tambahkan:

- `trading_mode`: `paper | live`
- `paper_initial_balance` atau referensi konfigurasi initial balance
- `compounding_enabled`
- `risk_per_trade`

### `paper_balances`

Balance virtual per user dan asset.

### `paper_orders`

Ledger order simulasi agar audit paper trading lengkap.

`positions` tetap menjadi sumber data posisi untuk dashboard. Tambahkan `mode` (`paper`/`live`) agar data tidak ambigu dan query dapat dipisahkan.

`forecast_signals` juga sebaiknya memiliki `mode` atau referensi run/trading account sehingga hasil paper dan live dapat dibandingkan tanpa mencampur data.

## 7. Auth dan keamanan

Gunakan Supabase Auth, RLS, MFA/2FA, dan validasi session token pada FastAPI seperti konsep asli.

Aturan tambahan untuk mode:

1. Akun baru selalu `paper`.
2. Paper mode tidak pernah membaca secret live untuk melakukan order.
3. Pergantian ke live harus eksplisit.
4. Secret Indodax tidak pernah dikirim ke frontend.
5. API key Indodax tidak diberi permission withdrawal.
6. `.env` masuk `.gitignore`.

## 8. Indodax integration

`indodax/client.py` tetap menjadi wrapper API Indodax.

Market-data/public API dipakai oleh kedua mode agar paper trading menggunakan kondisi pasar yang sama dengan live.

Private API hanya boleh digunakan oleh `LiveTradingGateway`.

```text
Public market data
       |
       +----> Forecast Agent
       |
       +----> PaperTradingGateway
       |
       +----> LiveTradingGateway reference

Private Indodax API
       |
       +----> LiveTradingGateway ONLY
```

## 9. Struktur folder

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
├── docs/
│   └── arsitektur-bot-scalping-indodax.md
├── .env.example
├── .gitignore
└── requirements.txt
```

## 10. Lifecycle yang harus identik

Paper dan live harus melewati pipeline berikut:

```text
Market Data
    ↓
Forecast Agent
    ↓
Forecast Signal
    ↓
Scalping Library
    ↓
Validated Trade Decision
    ↓
Executor Agent
    ↓
TradingGateway
    ├── PAPER → virtual execution
    └── LIVE  → Indodax execution
    ↓
Position Manager
    ↓
TP / SL / Manual Close
    ↓
PnL + Balance
    ↓
Trade Logs
    ↓
Supabase Realtime
    ↓
Dashboard
```

Tidak boleh ada jalur khusus yang melewati validation, risk control, position tracking, atau logging hanya karena mode paper.

## 11. Risk control

Konsep asli tetap berlaku:

- TP/SL dinamis berdasarkan volatilitas/ATR.
- Risk per trade.
- Compounding bertahap.
- Daily loss limit.
- Maksimal 6 coin aktif per user.

Daily loss limit harus bekerja di paper maupun live. Jika limit tercapai, Executor tidak boleh membuka posisi baru sampai periode berikutnya sesuai aturan sistem.

## 12. Reset environment

Karena FastAPI dan Supabase dinyatakan reset, implementasi dimulai dari fondasi kosong. Jangan membawa kode lama secara diam-diam.

Urutan pembangunan:

1. Repository dan struktur proyek kosong.
2. FastAPI health check.
3. Supabase connection + Auth + RLS.
4. Indodax public market data.
5. Forecast Agent.
6. Dashboard realtime.
7. Scalping Library.
8. Paper Trading Gateway + virtual balance.
9. Full paper lifecycle.
10. Live Trading Gateway.
11. Live safety gates.
12. Compounding + daily loss limit.

## 13. Prinsip pengujian

Setiap fitur trading harus dapat diuji dalam paper mode terlebih dahulu. Paper mode bukan versi sederhana yang hanya mencatat sinyal; ia harus menguji lifecycle trading sedekat mungkin dengan live.

Perbedaan yang memang tidak dapat dibuat identik adalah kondisi eksternal pasar dan execution nyata seperti latency, liquidity, fill aktual, dan slippage nyata. Simulator harus membuat asumsi tersebut eksplisit dan dapat dikonfigurasi.

## 14. Target akhir

Satu strategi, satu pipeline, satu Executor Agent, dua mode eksekusi:

```text
                 ┌── PAPER ──> Virtual Balance
Strategy ────────┤
                 └── LIVE  ──> Indodax Balance
```

Dengan demikian pengujian paper dapat menjadi tahap sebelum live tanpa harus membangun ulang strategi atau dashboard.
