"""Settings from environment variables, falling back to .env. Defaults suit local development."""

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Harness validation only (see voice_order/agent/faults.py).
Fault = Literal["none", "no_barge_in", "drop_modifiers", "aggressive_eou", "slow_llm"]
AGGRESSIVE_EOU_MS = 150


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
    tts_format: Literal["mp3", "pcm"] = "mp3"  # pcm skips decoding before playback
    # cascade: speech-to-text, the LLM, then text-to-speech. realtime: one OpenAI model hears
    # and speaks, with the same tools (the speech-to-speech experiment, E2).
    pipeline: Literal["cascade", "realtime"] = "cascade"
    realtime_model: str = "gpt-realtime-mini"
    realtime_voice: str = "marin"
    # Local speech instead of OpenAI's (see docs/adr/0007-local-speech.md)
    stt_provider: Literal["openai", "whisper"] = "whisper"
    whisper_model: str = "base.en"  # small.en is more accurate but ~1.4 s per utterance on CPU
    tts_provider: Literal["openai", "kokoro"] = "kokoro"
    kokoro_voice: str = "af_heart"
    models_dir: str = "models"  # local model files, downloaded with make models
    eou_silence_ms: int = Field(default=500, ge=0)  # silence before a turn may end
    # semantic: LiveKit's local turn model also judges whether the sentence sounds finished.
    # vad: the turn ends on silence alone.
    turn_detection: Literal["semantic", "vad"] = "semantic"
    # Silence that ends an utterance for voice detection. With local Whisper, recognition
    # only starts after it, so it sits directly in the end-of-turn delay.
    vad_min_silence_ms: int = Field(default=550, ge=100)
    enable_preemptive_generation: bool = True  # see docs/adr/0004-voice-pipeline.md
    enable_filler_phrases: bool = False
    filler_after_ms: int = Field(default=1200, ge=0)  # tool calls slower than this get a filler
    max_call_seconds: int = Field(default=300, gt=0)
    idle_timeout_seconds: int = Field(default=30, gt=0)  # caller silent this long: end the call
    # Limits on starting calls, for a public demo (see docs/adr/0008-demo-limits.md). 0 = none.
    calls_per_ip_per_hour: int = Field(default=0, ge=0)
    calls_per_day: int = Field(default=0, ge=0)
    trust_proxy: bool = False  # take the caller's IP from X-Forwarded-For (behind a proxy)
    fault: Fault = "none"  # breaks the voice worker on purpose, to test the eval harness

    # Observability and output
    phoenix_collector_endpoint: str = "http://localhost:6006"
    recordings_dir: str = "recordings"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.get_secret_value().strip())

    @property
    def effective_turn_detection(self) -> str:
        return "vad" if self.fault == "aggressive_eou" else self.turn_detection

    @property
    def effective_eou_silence_ms(self) -> int:
        return AGGRESSIVE_EOU_MS if self.fault == "aggressive_eou" else self.eou_silence_ms

    @property
    def speech_providers(self) -> tuple[str, str]:
        """Who hears and who speaks, as recorded with each call: costs differ by orders of
        magnitude between them, so cost estimates only compare calls with the same pair."""
        if self.pipeline == "realtime":
            return "realtime", "realtime"
        return self.stt_provider, self.tts_provider

    def stt_choice(self) -> tuple[str, str]:
        """(provider, model) for speech-to-text."""
        if self.pipeline == "realtime":
            return "openai", self.realtime_model
        if self.stt_provider == "whisper":
            return "local", self.whisper_model
        return "openai", self.stt_model

    def tts_choice(self) -> tuple[str, str]:
        """(provider, model) for text-to-speech."""
        if self.pipeline == "realtime":
            return "openai", self.realtime_model
        if self.tts_provider == "kokoro":
            return "local", "kokoro-v1.0"
        return "openai", self.tts_model

    def voice_config(self) -> dict[str, Any]:
        """The settings that shape a voice call, saved with each one so runs can be compared."""
        realtime = self.pipeline == "realtime"
        if realtime:
            voice = self.realtime_voice
        else:
            voice = self.kokoro_voice if self.tts_provider == "kokoro" else self.tts_voice
        return {
            "pipeline": self.pipeline,
            "llm_model": self.realtime_model if realtime else self.llm_model,
            "stt_provider": self.speech_providers[0],
            "stt_model": self.stt_choice()[1],
            "tts_provider": self.speech_providers[1],
            "tts_model": self.tts_choice()[1],
            "tts_voice": voice,
            "tts_format": self.tts_format,
            "eou_silence_ms": self.effective_eou_silence_ms,
            "turn_detection": self.effective_turn_detection,
            "vad_min_silence_ms": self.vad_min_silence_ms,
            "preemptive_generation": self.enable_preemptive_generation,
            "filler_phrases": self.enable_filler_phrases,
            "filler_after_ms": self.filler_after_ms,
            "fault": self.fault,
        }


@lru_cache
def get_settings() -> Settings:
    """Read the environment once per process."""
    return Settings()
