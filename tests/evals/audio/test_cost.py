"""The audio run cost estimate and the --yes rule."""

import json
from pathlib import Path

from evals.audio.cost import (
    YES_ABOVE_RUNS_UNKNOWN,
    YES_ABOVE_USD,
    Estimate,
    estimate,
    past_call_costs,
)


def _usage(root: Path, name: str, cost: object) -> None:
    folder = root / name
    folder.mkdir()
    (folder / "usage.json").write_text(json.dumps({"total_cost_usd": cost}))


def test_past_costs_come_from_audio_eval_calls_only(tmp_path: Path) -> None:
    _usage(tmp_path, "audio-a-r1", 0.04)
    _usage(tmp_path, "audio-b-r1", 0.06)
    _usage(tmp_path, "call-browser", 0.50)  # a dev call, not an eval run
    _usage(tmp_path, "audio-c-r1", None)  # unpriced
    (tmp_path / "audio-d-r1").mkdir()  # call still running, no usage yet
    (tmp_path / "audio-e-r1").mkdir()
    (tmp_path / "audio-e-r1" / "usage.json").write_text("{not json")
    assert past_call_costs(tmp_path) == [0.04, 0.06]


def test_estimate_scales_the_median_call() -> None:
    e = estimate(10, [0.02, 0.05, 0.50])
    assert e.usd == 0.5
    assert "3 earlier audio calls" in e.basis


def test_no_history_gives_no_number() -> None:
    e = estimate(10, [])
    assert e.usd is None
    assert "no earlier audio calls" in e.basis


def test_yes_needed_above_the_threshold() -> None:
    assert not Estimate(YES_ABOVE_USD, "").needs_yes(100)
    assert Estimate(YES_ABOVE_USD + 0.01, "").needs_yes(1)


def test_yes_needed_for_many_runs_without_history() -> None:
    assert not Estimate(None, "").needs_yes(YES_ABOVE_RUNS_UNKNOWN)
    assert Estimate(None, "").needs_yes(YES_ABOVE_RUNS_UNKNOWN + 1)


def test_only_calls_with_the_same_speech_providers_count(tmp_path: Path) -> None:
    _usage(tmp_path, "audio-hosted-r1", 0.08)  # no config.json: from before it was saved
    _usage(tmp_path, "audio-local-r1", 0.002)
    (tmp_path / "audio-local-r1" / "config.json").write_text(
        json.dumps({"stt_provider": "whisper", "tts_provider": "kokoro"})
    )
    assert past_call_costs(tmp_path) == [0.08]
    assert past_call_costs(tmp_path, ("whisper", "kokoro")) == [0.002]


def test_basis_mentions_caller_speech_only_when_paid() -> None:
    assert "speech" in estimate(1, [0.1]).basis
    assert "speech" not in estimate(1, [0.1], caller_speech_paid=False).basis
