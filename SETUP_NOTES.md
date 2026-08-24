# Catatan Perbaikan Struktur (dibuat otomatis)

## Yang diperbaiki
1. Semua file dipindah ke folder sesuai `import`-nya masing-masing
   (core/, agents/, backend/, exchange_integration/, paper_trading/, integration/).
2. Ditambahkan `__init__.py` di tiap folder package.
3. Dihapus `sys.path.append(...)` hack di `backend/routes/auth.py` dan
   `core/executor.py` — tidak diperlukan lagi karena struktur sudah benar.
4. Dibuat `exchange_integration/alpaca_bridge.py` (SKELETON) — file ini
   di-import oleh `core/executor.py` dan `core/market_data_adapter.py`
   tapi sebelumnya tidak ada sama sekali di project, sehingga aplikasi
   akan gagal start. Isinya masih placeholder (raise NotImplementedError),
   AMAN untuk mode paper, tapi HARUS diisi sebelum live trading sungguhan.
5. Bug: `core/orchestrator.py` dan `integration/trading_engine.py`
   memakai `config.get(...)` padahal `config` bisa `None`
   (harusnya `self.config.get(...)`). Ini akan menyebabkan
   `AttributeError: 'NoneType' object has no attribute 'get'` begitu
   `Orchestrator()` atau `TradingIntegrationEngine()` dipanggil tanpa
   argumen (persis seperti di `backend/routes/dashboard.py`). Sudah diperbaiki.

## Cara menjalankan (dari folder root project ini)

```bash
# 1. Install semua dependency
pip install -r requirements.txt

# 2. Copy .env.example -> .env lalu isi API key / secret Anda
cp .env.example .env

# 3A. Jalankan backend API (FastAPI)
uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000

# 3B. ATAU jalankan analisa satu kali lewat main.py
python main.py

# 3C. ATAU jalankan test 50-cycle
python test_multi_cycle.py
```

## Yang BELUM selesai (untuk sesi berikutnya)
- `exchange_integration/alpaca_bridge.py` masih skeleton, belum
  benar-benar konek ke Alpaca API.
- Keamanan: default JWT secret, default admin/admin123, CORS "*".
- `core/executor.py` (jalur eksekusi lama) vs `paper_trading/paper_engine.py`
  (dipakai oleh `integration/trading_engine.py`) masih dua jalur terpisah,
  perlu disatukan.
- Sentiment agent (news/social) masih placeholder (return 0.0).
