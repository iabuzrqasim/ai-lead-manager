"""Application settings, loaded from environment variables or a .env file.

Every value has a safe default so the app runs out of the box.
Secrets (API keys, SMTP password, JWT secret) must be set in .env, never in code.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "AI Lead Manager"
    company_name: str = "TechNest Nova"
    environment: str = "development"

    # Database: SQLite by default; set a postgresql+psycopg:// URL to switch.
    database_url: str = "sqlite:///./leads.db"

    # Auth
    secret_key: str = "dev-only-secret-change-me-before-deploying-0000"
    access_token_expire_minutes: int = 60 * 8
    admin_email: str = "admin@technestnova.com"
    admin_password: str = "admin12345"

    # Follow-up scheduler
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60

    # AI drafts (optional). Without a key, a built-in template is used.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    ai_timeout_seconds: float = 30.0

    # Email sending (optional, OFF by default)
    email_sending_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    # Safety net: while set, every email goes to this inbox instead of the lead.
    email_test_inbox: str = ""

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
