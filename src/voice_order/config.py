"""Settings from environment variables, falling back to .env. Defaults suit local development."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env. Other keys in .env are ignored.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://voice:voice@localhost:5432/voice_order"

    # SecretStr prints as '**********'; use .get_secret_value() where the key is actually sent.
    openai_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-6-luna"
    caller_llm_model: str = "gpt-6-luna"

    # LiveKit (local dev server defaults)
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: SecretStr = SecretStr("secret")
    agent_name: str = "order-agent"  # explicit dispatch: tokens ask for this agent by name

    # Voice pipeline (see docs/adr/0004-voice-pipeline.md)
    stt_model: str = "gpt-live-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "coral"
    eou_silence_ms: int = Field(default=500, ge=0)  # silence before a turn may end
    enable_preemptive_generation: bool = False  # on, it sometimes said a sentence twice
    enable_filler_phrases: bool = False
    filler_after_ms: int = Field(default=1200, ge=0)  # tool calls slower than this get a filler
    max_call_seconds: int = Field(default=300, gt=0)
    idle_timeout_seconds: int = Field(default=30, gt=0)  # caller silent this long: end the call

    # Observability and output
    phoenix_collector_endpoint: str = "http://localhost:6006"
    recordings_dir: str = "recordings"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    """Read the environment once per process."""
    return Settings()
