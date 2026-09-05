from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "AI Multi-Agent Trading Bot"
    environment: str = "production"
    trading_mode: str = "paper"
    api_prefix: str = ""
    cors_origins: str = "https://doushitekana62-ship-it.github.io,http://localhost:8000,http://127.0.0.1:8000"
    supabase_url: str = "https://qsapzacpahoppposcbxc.supabase.co"
    supabase_publishable_key: str = "sb_publishable_KGcA_9AO6V_QbG6mKaXkrw_XQswjsK_"
    supabase_secret_key: str = ""
    supabase_service_role_key: str = ""
    jwt_secret_key: str = ""
    indodax_public_url: str = "https://indodax.com/api"
    indodax_private_url: str = "https://indodax.com/tapi"
    indodax_api_key: str = ""
    indodax_secret_key: str = ""
    default_risk_per_trade: float = 0.5
    daily_loss_limit_percent: float = 3.0
    max_allocated_coins: int = 6
    paper_initial_balance: float = 1_000_000.0
    paper_fee_percent: float = 0.3
    paper_slippage_percent: float = 0.05
    scheduler_interval_seconds: int = 5
    min_signal_confidence: float = 0.62
    signal_min_score: float = 80.0
    max_drawdown_percent: float = 5.0
    max_total_open_risk_percent: float = 1.5
    max_loss_streak: int = 3
    cooldown_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
