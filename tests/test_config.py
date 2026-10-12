"""Settings loading. These tests never read the developer's real .env."""

from pathlib import Path

import pytest

from voice_order.config import Settings, get_settings

ENV_VARS = [
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "LLM_MODEL",
    "CALLER_LLM_MODEL",
    "EOU_SILENCE_MS",
    "ENABLE_PREEMPTIVE_GENERATION",
    "MAX_CALL_SECONDS",
    "LIVEKIT_API_SECRET",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_env_file() -> None:
    s = Settings(_env_file=None)
    assert s.llm_model == s.caller_llm_model == "gpt-6-luna"
    assert s.database_url.startswith("postgresql://")
    assert not s.has_openai_key


def test_environment_variables_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    s = Settings(_env_file=None)
    assert s.llm_model == "gpt-6.1-sol"
    assert s.has_openai_key


def test_env_file_is_read_and_env_vars_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=from-file\nCALLER_LLM_MODEL=caller-from-file\nPOSTGRES_DB=x\n")
    monkeypatch.setenv("LLM_MODEL", "from-env")
    s = Settings(_env_file=env_file)
    assert (s.llm_model, s.caller_llm_model) == ("from-env", "caller-from-file")


def test_api_key_is_masked_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    s = Settings(_env_file=None)
    for text in (repr(s), str(s), str(s.model_dump())):
        assert "sk-test-secret-value" not in text
    assert s.openai_api_key.get_secret_value() == "sk-test-secret-value"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_key_counts_as_missing(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", value)
    assert not Settings(_env_file=None).has_openai_key


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_voice_defaults() -> None:
    s = Settings(_env_file=None)
    assert (s.eou_silence_ms, s.max_call_seconds) == (500, 300)
    assert s.enable_preemptive_generation is True
    assert s.livekit_url.startswith("ws://")


def test_livekit_secret_is_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-test-secret-value")
    s = Settings(_env_file=None)
    assert "lk-test-secret-value" not in repr(s)
    assert s.livekit_api_secret.get_secret_value() == "lk-test-secret-value"


def test_voice_knobs_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EOU_SILENCE_MS", "150")
    monkeypatch.setenv("ENABLE_PREEMPTIVE_GENERATION", "false")
    s = Settings(_env_file=None)
    assert (s.eou_silence_ms, s.enable_preemptive_generation) == (150, False)


def test_every_setting_is_documented_in_env_example() -> None:
    documented = {
        line.split("=", 1)[0]
        for line in (Path(__file__).parents[1] / ".env.example").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = sorted(
        name.upper() for name in Settings.model_fields if name.upper() not in documented
    )
    assert not missing, f"add these to .env.example: {missing}"


def test_voice_config_names_what_shapes_a_call() -> None:
    config = Settings(_env_file=None, eou_silence_ms=300).voice_config()
    assert config["eou_silence_ms"] == 300
    assert config["preemptive_generation"] is True
    assert {"llm_model", "stt_model", "tts_model", "tts_voice"} <= set(config)


def test_local_speech_by_default() -> None:
    s = Settings(_env_file=None)
    assert s.stt_choice() == ("local", "base.en")
    assert s.tts_choice() == ("local", "kokoro-v1.0")


def test_openai_speech_is_one_setting_away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "openai")
    monkeypatch.setenv("TTS_PROVIDER", "openai")
    s = Settings(_env_file=None)
    assert s.stt_choice() == ("openai", "gpt-live-transcribe")
    assert s.tts_choice() == ("openai", "gpt-4o-mini-tts")


def test_local_speech_is_named_in_the_saved_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_MODEL", "base.en")
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setenv("KOKORO_VOICE", "bf_emma")
    config = Settings(_env_file=None).voice_config()
    assert (config["stt_provider"], config["stt_model"]) == ("whisper", "base.en")
    assert (config["tts_provider"], config["tts_model"], config["tts_voice"]) == (
        "kokoro",
        "kokoro-v1.0",
        "bf_emma",
    )


def test_vad_silence_is_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).voice_config()["vad_min_silence_ms"] == 550
    monkeypatch.setenv("VAD_MIN_SILENCE_MS", "300")
    assert Settings(_env_file=None).vad_min_silence_ms == 300


def test_turn_detection_is_a_setting_and_the_fault_overrides_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).voice_config()["turn_detection"] == "semantic"
    monkeypatch.setenv("TURN_DETECTION", "vad")
    assert Settings(_env_file=None).effective_turn_detection == "vad"
    monkeypatch.setenv("TURN_DETECTION", "semantic")
    monkeypatch.setenv("FAULT", "aggressive_eou")
    assert Settings(_env_file=None).effective_turn_detection == "vad"
