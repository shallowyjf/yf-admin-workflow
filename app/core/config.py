"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "统一权限与流程工单平台"
    environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./var/demo.db"
    auth_cookie_name: str = "yf_session"
    auth_cookie_secure: bool = False
    auth_session_hours: int = 8
    default_tenant_code: str = "DEMO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
