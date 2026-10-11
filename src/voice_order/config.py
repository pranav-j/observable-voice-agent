"""Settings from environment variables, falling back to .env. Defaults suit local development."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env. Other keys in .env are ignored.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://voice:voice@localhost:5432/voice_order"

    # SecretStr prints as '**********'; use .get_secret_value() where the key is actually sent.
    openai_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-6-luna"
    caller_llm_model: str = "gpt-6-luna"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    """Read the environment once per process."""
    return Settings()
