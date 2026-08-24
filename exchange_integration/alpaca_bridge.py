"""
exchange_integration/alpaca_bridge.py

Jembatan (bridge) ke Alpaca API untuk LIVE / PAPER trading via broker Alpaca.

STATUS: SKELETON / BELUM DIIMPLEMENTASIKAN PENUH.

File ini sebelumnya di-import oleh core/executor.py dan
core/market_data_adapter.py tapi belum ada di source project,
sehingga aplikasi akan gagal start (ImportError) tanpa file ini.

Skeleton di bawah ini SENGAJA dibuat "aman" (fail gracefully / raise
NotImplementedError) supaya:
1. Semua import di seluruh project tetap berhasil.
2. Mode PAPER (exchange_integration/paper_trading.py) tetap berjalan
   normal tanpa butuh API key apapun.
3. Ketika Anda siap menyambungkan ke akun Alpaca sungguhan, tinggal
   isi bagian TODO di bawah ini.

Referensi resmi: https://docs.alpaca.markets/
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class AlpacaBridge:
    """
    Bridge ke Alpaca Trading API.

    Dipakai untuk:
    - Ambil harga & data historis (get_current_price, get_historical_data)
    - Kirim order (submit_order)
    - Ambil nilai akun (get_account_value)

    PENTING (safety):
    - Selama ALPACA_API_KEY / ALPACA_SECRET_KEY belum di-set di .env,
      class ini tidak akan bisa melakukan apa-apa selain melempar error
      yang jelas. Ini supaya tidak ada eksekusi order tanpa sengaja.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        self.api_key = self.config.get("api_key") or os.getenv("ALPACA_API_KEY")
        self.secret_key = self.config.get("secret_key") or os.getenv("ALPACA_SECRET_KEY")
        self.base_url = (
            self.config.get("base_url")
            or os.getenv("ALPACA_API_URL", "https://paper-api.alpaca.markets")
        )
        self.paper = str(os.getenv("ALPACA_PAPER", "True")).lower() in ("1", "true", "yes")

        self._client = None
        self._is_configured = bool(self.api_key and self.secret_key)

        if not self._is_configured:
            logger.warning(
                "AlpacaBridge belum dikonfigurasi (ALPACA_API_KEY / "
                "ALPACA_SECRET_KEY kosong). Semua method akan gagal "
                "sampai kredensial diisi di .env."
            )
        else:
            logger.info(
                "AlpacaBridge dikonfigurasi | base_url=%s | paper=%s",
                self.base_url, self.paper
            )

    # ============================================================
    # INTERNAL CLIENT (lazy init)
    # ============================================================

    def _ensure_client(self):
        """
        Inisialisasi client Alpaca secara lazy (hanya saat dibutuhkan).

        TODO: pilih salah satu SDK resmi, misalnya:
            pip install alpaca-py
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

        atau pakai REST langsung dengan `requests` ke:
            {base_url}/v2/account
            {base_url}/v2/orders
            data.alpaca.markets/v2/stocks/{symbol}/bars
        """
        if not self._is_configured:
            raise RuntimeError(
                "AlpacaBridge belum dikonfigurasi. Set ALPACA_API_KEY dan "
                "ALPACA_SECRET_KEY di file .env terlebih dahulu."
            )

        if self._client is None:
            # TODO: ganti dengan inisialisasi SDK/HTTP client sungguhan.
            raise NotImplementedError(
                "Koneksi live ke Alpaca belum diimplementasikan. "
                "Ini masih skeleton — isi bagian ini saat siap live trading."
            )

        return self._client

    # ============================================================
    # PUBLIC METHODS (dipakai oleh core/executor.py & market_data_adapter.py)
    # ============================================================

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Ambil harga terkini untuk simbol tertentu dari Alpaca."""
        self._ensure_client()
        raise NotImplementedError("get_current_price belum diimplementasikan.")

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Ambil data OHLCV historis dari Alpaca."""
        self._ensure_client()
        raise NotImplementedError("get_historical_data belum diimplementasikan.")

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market"
    ) -> Optional[Dict[str, Any]]:
        """
        Kirim order ke Alpaca.

        PERINGATAN: Ini akan mengeksekusi order SUNGGUHAN (atau paper,
        tergantung ALPACA_PAPER) begitu diimplementasikan. Pastikan
        RiskEngine, DecisionEngine, dan ExecutionGate sudah diuji habis
        di mode paper sebelum method ini diisi & dipakai.
        """
        self._ensure_client()
        raise NotImplementedError("submit_order belum diimplementasikan.")

    def get_account_value(self) -> float:
        """Ambil total nilai akun (equity) dari Alpaca."""
        self._ensure_client()
        raise NotImplementedError("get_account_value belum diimplementasikan.")

    def is_configured(self) -> bool:
        """Cek apakah kredensial Alpaca sudah di-set."""
        return self._is_configured
