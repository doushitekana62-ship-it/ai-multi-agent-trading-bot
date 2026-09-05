import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Compound Scalping API")
    app_version: str = os.getenv("APP_VERSION", "2.1.0")
    cors_origins: str = os.getenv("CORS_ORIGINS", "")

    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    # Accept DATABASE_URL for common hosting platforms, while keeping the
    # explicit SUPABASE_DB_URL name for local deployments.
    supabase_db_url: str = os.getenv("SUPABASE_DB_URL", os.getenv("DATABASE_URL", ""))
    bot_owner_user_id: str = os.getenv("BOT_OWNER_USER_ID", "")

    # Exchange / Freqtrade. Market-data mode uses a public exchange endpoint;
    # no exchange secret is required while TRADING_MODE=paper.
    exchange_name: str = os.getenv("EXCHANGE_NAME", "bybit")
    trading_mode: str = os.getenv("TRADING_MODE", "paper").lower()
    bot_name: str = os.getenv("BOT_NAME", "compound-scalper")
    strategy_name: str = os.getenv("FREQTRADE_STRATEGY", "CompoundScalpingStrategy")
    trading_pairs: str = os.getenv("TRADING_PAIRS", "BTC/USDT")
    stake_currency: str = os.getenv("STAKE_CURRENCY", "USDT")
    stake_amount: float = float(os.getenv("STAKE_AMOUNT", "100"))
    paper_initial_balance: float = float(os.getenv("PAPER_INITIAL_BALANCE", "1000"))
    max_open_trades: int = int(os.getenv("MAX_OPEN_TRADES", "1"))
    timeframe: str = os.getenv("TIMEFRAME", "1m")
    process_throttle_secs: float = float(os.getenv("PROCESS_THROTTLE_SECS", "5"))
    heartbeat_interval: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"


settings = Settings()
