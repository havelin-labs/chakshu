"""Process settings, read once from the environment.

Only things an operator must decide before the app starts live here. Everything
else (GitHub App credentials, API keys, defaults) is set in the portal and kept
in the database.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHAKSHU_", env_file=".env", extra="ignore")

    base_url: str = "http://localhost:8000"
    # Public URL GitHub sends webhooks to. Defaults to <base_url>/webhooks/github.
    # Point it at a smee.io channel when running on a laptop.
    webhook_url: str = ""
    secret_key: str = Field(default="", repr=False)
    database_url: str = "postgresql+asyncpg://chakshu:chakshu@localhost:5432/chakshu"
    # GitHub logins that are always admins, comma separated.
    admins: str = ""
    github_url: str = "https://github.com"
    github_api_url: str = "https://api.github.com"
    worker_concurrency: int = 2
    # Built React portal. The Docker image sets this; locally it's frontend/dist.
    frontend_dir: str = "frontend/dist"
    log_level: str = "INFO"

    @field_validator("base_url", "webhook_url", "github_url", "github_api_url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def hook_url(self) -> str:
        return self.webhook_url or f"{self.base_url}/webhooks/github"

    @property
    def admin_logins(self) -> set[str]:
        return {login.strip().lower() for login in self.admins.split(",") if login.strip()}

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
