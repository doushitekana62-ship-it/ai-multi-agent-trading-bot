import os
from dataclasses import dataclass


DEFAULT_FREQTRADE_DB_PATH = "/tmp/compound-scalping/tradesv3.sqlite"
SUPPORTED_EXCHANGE = "indodax"
DEFAULT_CORS_ORIGINS = "https://doushitekana62-ship-it.github.io"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Compound Scalping API")
    app_version: str = os.getenv("APP_VERSION", "2.4.0")
    # GitHub Pages is the production frontend. Keep the known origin enabled
    # by default so a missing CORS env var cannot break the dashboard.
    cors_origins: str = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    dashboard_token: str = os.getenv("DASHBOARD_TOKEN", "")
    freqtrade_db_path: str = os.getenv("FREQTRADE_DB_PATH", DEFAULT_FREQTRADE_DB_PATH)

    # This project is Indodax-only. Ignore stale exchange environment values
    # (for example BYBIT) so a deployment cannot silently target another venue.
    exchange_name: str = SUPPORTED_EXCHANGE
    trading_mode: str = os.getenv("TRADING_MODE", "paper").lower()
    bot_name: str = os.getenv("BOT_NAME", "compound-scalper")
    strategy_name: str = os.getenv("FREQTRADE_STRATEGY", "CompoundScalpingStrategy")
    trading_pairs: str = os.getenv("TRADING_PAIRS", "BTC/IDR")
    stake_currency: str = os.getenv("STAKE_CURRENCY", "IDR")
    stake_amount: float = float(os.getenv("STAKE_AMOUNT", "100000"))
    paper_initial_balance: float = float(os.getenv("PAPER_INITIAL_BALANCE", "1000000"))
    max_open_trades: int = int(os.getenv("MAX_OPEN_TRADES", "1"))
    timeframe: str = os.getenv("TIMEFRAME", "1m")
    process_throttle_secs: float = float(os.getenv("PROCESS_THROTTLE_SECS", "5"))
    heartbeat_interval: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

    indodax_api_key: str = os.getenv("INDODAX_API_KEY", "")
    indodax_api_secret: str = os.getenv("INDODAX_API_SECRET", "")
    live_trading_enabled: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

    runtime_restart_enabled: bool = os.getenv("RUNTIME_RESTART_ENABLED", "false").lower() == "true"
    runtime_restart_delay: int = int(os.getenv("RUNTIME_RESTART_DELAY", "30"))

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def live_ready(self) -> bool:
        return self.is_live and self.live_trading_enabled and bool(self.indodax_api_key and self.indodax_api_secret)


settings = Settings()
