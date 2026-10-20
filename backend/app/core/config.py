from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Apprentissage Langue"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    frontend_url: str = "http://localhost:3000"

    database_url: str = Field(
        default="postgresql+psycopg://apprentissage_app:apprentissage_dev@localhost:5433/apprentissage_langue",
        alias="DATABASE_URL",
    )
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_exp_minutes: int = 60
    refresh_token_exp_days: int = 14
    cookie_secure: bool = False
    cookie_domain: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
