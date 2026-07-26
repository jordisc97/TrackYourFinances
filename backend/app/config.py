from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "TrackYourFinances"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/finances.db"
    cors_origins: str = "http://localhost:5173"
    default_spend_pct: float = 50.0
    default_save_pct: float = 25.0
    default_invest_pct: float = 25.0
    enable_banking_app_id: str = ""
    enable_banking_private_key_path: str = ""
    enable_banking_base_url: str = "https://api.enablebanking.com"
    enable_banking_redirect_url: str = "http://localhost:8000/api/banking/callback"
    enable_banking_country: str = "ES"
    jwt_expire_minutes: int = 60 * 24 * 7
    jwt_algorithm: str = "HS256"
    deepseek_api: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"


@lru_cache
def get_settings() -> Settings:
    return Settings()
