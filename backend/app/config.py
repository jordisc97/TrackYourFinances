from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET_KEY = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "TrackYourFinances"
    env: str = "development"
    secret_key: str = DEFAULT_SECRET_KEY
    database_url: str = "sqlite:///./data/finances.db"
    cors_origins: str = "http://127.0.0.1:5174"
    static_dir: str = "static"
    auth_rate_limit_per_minute: int = 10
    min_password_length: int = 8
    default_spend_pct: float = 50.0
    default_save_pct: float = 25.0
    default_invest_pct: float = 25.0
    bank_provider: str = "gocardless"
    bank_country: str = "ES"
    enable_banking_app_id: str = ""
    enable_banking_private_key_path: str = ""
    enable_banking_base_url: str = "https://api.enablebanking.com"
    enable_banking_redirect_url: str = "http://127.0.0.1:8100/api/banking/callback"
    gc_secret_id: str = ""
    gc_secret_key: str = ""
    gc_base_url: str = "https://bankaccountdata.gocardless.com/api/v2"
    gc_redirect_url: str = "http://127.0.0.1:8100/api/banking/callback"
    jwt_expire_minutes: int = 60 * 24 * 7
    jwt_algorithm: str = "HS256"
    deepseek_api: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    categorize_interval_seconds: int = 900
    categorize_llm_limit: int = 50
    categorize_max_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
