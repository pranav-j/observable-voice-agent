"""The CI gate: compare a report's summary with the baseline, using gate.yaml margins."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from evals.gate import GATE, METRICS, Check, baseline_key, check, main, metrics_of


def summary(mode: str = "audio", **sections: dict[str, Any]) -> dict[str, Any]:
    base: dict[str, Any] = {
        "mode": mode,
        "started_at": "2026-10-11T12:00:00+00:00",
        "overall": {"runs": 10, "task_success_rate": 0.9, "order_exact_match_rate": 0.9},
        "audio": {"response_latency_ms_p95": 2000.0, "barge_in_stop_ms_p95": None},
        "judged": None,
    }
    for name, values in sections.items():
        base[name] = {**(base.get(name) or {}), **values}
    return base


def baseline_of(s: dict[str, Any]) -> dict[str, Any]:
    return {s["mode"]: {"metrics": metrics_of(s)}}


@pytest.mark.parametrize(
    ("rule", "baseline", "current", "status"),
    [
        ("max_drop", 0.90, 0.86, "pass"),
        ("max_drop", 0.90, 0.84, "fail"),
        ("max_increase", 2000.0, 2290.0, "pass"),
        ("max_increase", 2000.0, 2310.0, "fail"),
        ("max_increase_abs", 0.10, 0.24, "pass"),
        ("max_increase_abs", 0.10, 0.26, "fail"),
        ("max_drop", None, 0.5, "skipped"),
        ("max_increase", 2000.0, None, "skipped"),
    ],
)
def test_rules(rule: str, baseline: float | None, current: float | None, status: str) -> None:
    margin = {"max_drop": 0.05, "max_increase": 0.15, "max_increase_abs": 0.15}[rule]
    assert Check("m", baseline, current, rule, margin).status == status  # type: ignore[arg-type]


def test_slow_llm_style_regression_fails_the_gate() -> None:
    base = summary()
    slow = summary(audio={"response_latency_ms_p95": 2800.0})
    gate = {"audio": {"response_latency_ms_p95": {"max_increase": 0.15}}}
    (result,) = check(slow, baseline_of(base), gate)
    assert result.status == "fail"


def test_unmeasured_metrics_are_skipped_not_passed() -> None:
    gate = {"audio": {"barge_in_stop_ms_p95": {"max_increase": 0.25}}}
    (result,) = check(summary(), baseline_of(summary()), gate)
    assert result.status == "skipped"


def test_missing_baseline_for_the_mode_is_an_error() -> None:
    with pytest.raises(ValueError, match="no text baseline"):
        check(summary("text"), baseline_of(summary("audio")), {"text": {}})


def test_committed_gate_only_names_known_metrics() -> None:
    gate = yaml.safe_load(GATE.read_text())
    for mode in ("text", "audio"):
        for metric, rule in gate[mode].items():
            assert metric in METRICS
            ((kind, _),) = rule.items()
            assert kind in {"max_drop", "max_increase", "max_increase_abs"}


def _report(root: Path, s: dict[str, Any]) -> Path:
    root.mkdir(parents=True)
    (root / "summary.json").write_text(json.dumps(s))
    return root


def test_cli_updates_the_baseline_then_gates(tmp_path: Path) -> None:
    good = _report(tmp_path / "good", summary())
    bad = _report(tmp_path / "bad", summary(overall={"task_success_rate": 0.5}))
    baseline = tmp_path / "baseline.json"
    assert main([str(good), "--baseline", str(baseline), "--update-baseline"]) == 0
    assert json.loads(baseline.read_text())["audio"]["metrics"]["task_success_rate"] == 0.9
    assert main([str(good), "--baseline", str(baseline)]) == 0
    assert main([str(bad), "--baseline", str(baseline)]) == 1


def test_cli_without_a_baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _report(tmp_path / "r", summary())
    assert main([str(report), "--baseline", str(tmp_path / "none.json")]) == 2
    assert "no audio baseline" in capsys.readouterr().err


def test_local_speech_reports_get_their_own_baseline() -> None:
    local = summary(
        audio={"agent_configs": [{"stt_provider": "whisper", "tts_provider": "kokoro"}]}
    )
    hosted = summary(
        audio={"agent_configs": [{"stt_provider": "openai", "tts_provider": "openai"}]}
    )
    old = summary(audio={"agent_configs": [{"stt_model": "gpt-live-transcribe"}]})  # pre-providers
    assert baseline_key(local) == "audio:whisper+kokoro"
    assert baseline_key(hosted) == baseline_key(old) == "audio"
    with pytest.raises(ValueError, match="no audio:whisper\\+kokoro baseline"):
        check(local, baseline_of(hosted), {"audio": {}})


def test_a_report_mixing_speech_providers_is_refused() -> None:
    mixed = summary(
        audio={
            "agent_configs": [
                {"stt_provider": "openai", "tts_provider": "openai"},
                {"stt_provider": "whisper", "tts_provider": "kokoro"},
            ]
        }
    )
    with pytest.raises(ValueError, match="mixes speech providers"):
        baseline_key(mixed)
