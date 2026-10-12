"""Usage aggregation and cost from the rates file."""

from types import SimpleNamespace

import pytest

from voice_order.telemetry.usage import load_rates, summarize_usage


def usage(kind: str, model: str, **fields: float) -> SimpleNamespace:
    return SimpleNamespace(type=f"{kind}_usage", provider="openai", model=model, **fields)


def test_rates_file_loads_with_the_models_we_use() -> None:
    rates = load_rates()
    assert "openai/gpt-6-luna" in rates.llm
    assert "openai/gpt-live-transcribe" in rates.stt
    assert "openai/gpt-4o-mini-tts" in rates.tts


def test_cost_is_usage_times_rates() -> None:
    summary = summarize_usage(
        [
            usage(
                "llm",
                "gpt-6-luna",
                input_tokens=40_000,
                input_cached_tokens=10_000,
                output_tokens=2_000,
            ),
            usage("stt", "gpt-live-transcribe", audio_duration=120.0),
            usage(
                "tts",
                "gpt-4o-mini-tts",
                input_tokens=1_000,
                output_tokens=50_000,
                characters_count=900,
            ),
        ],
        load_rates(),
    )
    llm, stt, tts = summary["models"]
    # 30k fresh x $0.10 + 10k cached x $0.01 + 2k out x $0.50, per million
    assert llm["cost_usd"] == pytest.approx((30_000 * 0.10 + 10_000 * 0.01 + 2_000 * 0.50) / 1e6)
    assert stt["cost_usd"] == pytest.approx(2 * 0.017)  # two minutes
    assert tts["cost_usd"] == pytest.approx((1_000 * 0.60 + 50_000 * 12.00) / 1e6)
    assert summary["total_cost_usd"] == pytest.approx(
        llm["cost_usd"] + stt["cost_usd"] + tts["cost_usd"]
    )
    assert summary["unpriced"] == []


def test_models_without_a_rate_are_flagged_not_free() -> None:
    summary = summarize_usage(
        [usage("llm", "some-new-model", input_tokens=10, output_tokens=5)], load_rates()
    )
    assert summary["unpriced"] == ["openai/some-new-model"]
    assert summary["total_cost_usd"] == 0
    assert "cost_usd" not in summary["models"][0]


def test_provider_reported_as_api_host_still_matches_its_rates() -> None:
    reported = SimpleNamespace(
        type="stt_usage",
        provider="api.openai.com",
        model="gpt-live-transcribe",
        audio_duration=60.0,
    )
    summary = summarize_usage([reported], load_rates())
    assert summary["unpriced"] == []
    assert summary["models"][0]["model"] == "openai/gpt-live-transcribe"
    assert summary["total_cost_usd"] == pytest.approx(0.017)


def test_stt_without_a_reported_duration_falls_back_to_call_length() -> None:
    silent = SimpleNamespace(type="stt_usage", provider="openai", model="gpt-live-transcribe")
    line = summarize_usage([silent], load_rates(), call_seconds=120.0)["models"][0]
    assert line["estimated_from_call_length"] is True
    assert line["audio_seconds"] == 120.0
    assert line["cost_usd"] == pytest.approx(2 * 0.017)


def test_a_reported_stt_duration_is_used_as_is() -> None:
    reported = usage("stt", "gpt-live-transcribe", audio_duration=30.0)
    line = summarize_usage([reported], load_rates(), call_seconds=120.0)["models"][0]
    assert "estimated_from_call_length" not in line
    assert line["audio_seconds"] == 30.0


def test_speech_to_speech_prices_audio_and_text_tokens_apart() -> None:
    summary = summarize_usage(
        [
            usage(
                "llm",
                "gpt-realtime-mini",
                input_tokens=12_000,
                input_cached_tokens=8_000,
                input_text_tokens=9_000,
                input_cached_text_tokens=7_000,
                input_audio_tokens=3_000,
                input_cached_audio_tokens=1_000,
                output_tokens=2_500,
                output_text_tokens=500,
                output_audio_tokens=2_000,
            )
        ],
        load_rates(),
    )
    (line,) = summary["models"]
    expected = (
        2_000 * 0.60 + 7_000 * 0.06 + 2_000 * 10.00 + 1_000 * 0.30 + 500 * 2.40 + 2_000 * 20.00
    ) / 1e6
    assert line["cost_usd"] == pytest.approx(expected)
    assert (line["input_audio_tokens"], line["output_audio_tokens"]) == (3_000, 2_000)


def test_text_only_models_keep_the_plain_formula() -> None:
    summary = summarize_usage(
        [usage("llm", "gpt-6-luna", input_tokens=1_000_000, output_tokens=100_000)], load_rates()
    )
    assert summary["models"][0]["cost_usd"] == pytest.approx(0.10 + 0.05)
    assert "input_audio_tokens" not in summary["models"][0]
