import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv('APP_NAME','Compound Scalping API')
    cors_origins: str = os.getenv('CORS_ORIGINS','*')
    freqtrade_url: str = os.getenv('FREQTRADE_URL','http://freqtrade:8080/api/v1')
    freqtrade_username: str = os.getenv('FREQTRADE_USERNAME','')
    freqtrade_password: str = os.getenv('FREQTRADE_PASSWORD','')
    supabase_url: str = os.getenv('SUPABASE_URL','')
    supabase_anon_key: str = os.getenv('SUPABASE_ANON_KEY','')
    supabase_service_role_key: str = os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
settings=Settings()
