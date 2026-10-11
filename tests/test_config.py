"""Settings loading. These tests never read the developer's real .env."""

from pathlib import Path

import pytest

from voice_order.config import Settings, get_settings

ENV_VARS = ["DATABASE_URL", "OPENAI_API_KEY", "LLM_MODEL", "CALLER_LLM_MODEL"]


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
