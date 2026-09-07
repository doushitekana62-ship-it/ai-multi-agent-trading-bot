import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FREQTRADE_DB_PATH = str(_PROJECT_DIR / "data" / "tradesv3.sqlite")
SUPPORTED_EXCHANGE = "indodax"
DEFAULT_TRADING_PAIR = "BTC/IDR"
FREQTRADE_API_USERNAME = "doushitekana"
DEFAULT_CORS_ORIGINS = "https://doushitekana62-ship-it.github.io"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Compound Scalping API")
    app_version: str = os.getenv("APP_VERSION", "2.5.2")
    cors_origins: str = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    dashboard_token: str = os.getenv("DASHBOARD_TOKEN", "")
    freqtrade_db_path: str = os.getenv("FREQTRADE_DB_PATH", DEFAULT_FREQTRADE_DB_PATH)
    freqtrade_api_port: int = int(os.getenv("FREQTRADE_API_PORT", "8080"))
    freqtrade_api_username: str = FREQTRADE_API_USERNAME
    freqtrade_jwt_secret: str = os.getenv("FREQTRADE_JWT_SECRET", "")
    freqtrade_internal_password: str = os.getenv("FREQTRADE_INTERNAL_PASSWORD", "")

    exchange_name: str = SUPPORTED_EXCHANGE
    trading_mode: str = os.getenv("TRADING_MODE", "paper").lower()
    bot_name: str = os.getenv("BOT_NAME", "compound-scalper")
    strategy_name: str = os.getenv("FREQTRADE_STRATEGY", "CompoundScalpingStrategy")
    trading_pairs: str = DEFAULT_TRADING_PAIR
    stake_currency: str = "IDR"
    stake_amount: float = float(os.getenv("STAKE_AMOUNT", "100000"))
    paper_initial_balance: float = float(os.getenv("PAPER_INITIAL_BALANCE", "1000000"))
    max_open_trades: int = int(os.getenv("MAX_OPEN_TRADES", "1"))
    timeframe: str = os.getenv("TIMEFRAME", "1m")
    # Freqtrade's schema requires this to be an integer.
    process_throttle_secs: int = int(os.getenv("PROCESS_THROTTLE_SECS", "5"))
    heartbeat_interval: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

    indodax_api_key: str = os.getenv("INDODAX_API_KEY", "")
    indodax_api_secret: str = os.getenv("INDODAX_API_SECRET", "")
    live_trading_enabled: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

    # Paper mode starts automatically. Live mode never auto-starts.
    auto_start_trading: bool = os.getenv("AUTO_START_TRADING", "true").lower() == "true"
    runtime_restart_enabled: bool = os.getenv("RUNTIME_RESTART_ENABLED", "true").lower() == "true"
    runtime_restart_delay: int = int(os.getenv("RUNTIME_RESTART_DELAY", "30"))

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def live_ready(self) -> bool:
        return self.is_live and self.live_trading_enabled and bool(self.indodax_api_key and self.indodax_api_secret)

    @property
    def should_auto_start(self) -> bool:
        return self.auto_start_trading and not self.is_live and not self.live_ready

    @property
    def effective_freqtrade_jwt_secret(self) -> str:
        if self.freqtrade_jwt_secret:
            return self.freqtrade_jwt_secret
        seed = self.dashboard_token or self.freqtrade_internal_password or f"paper:{self.bot_name}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    @property
    def effective_freqtrade_internal_password(self) -> str:
        if self.freqtrade_internal_password:
            return self.freqtrade_internal_password
        seed = self.dashboard_token or self.effective_freqtrade_jwt_secret
        return hashlib.sha256(f"{seed}:freqtrade-api".encode("utf-8")).hexdigest()


settings = Settings()
