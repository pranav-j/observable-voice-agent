"""Before/after tables for experiment and validation write-ups."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from evals.compare import compare, load_summary, main
from evals.report import write_report

from tests.evals.test_report import result


def summary(latency: float, config: dict[str, Any], mode: str = "audio") -> dict[str, Any]:
    return {
        "mode": mode,
        "overall": {"runs": 6, "task_success_rate": 0.5},
        "audio": {"response_latency_ms_p95": latency, "agent_configs": [config]},
    }


def test_table_shows_both_sides_and_the_change() -> None:
    table = compare(summary(2000, {"fault": "none"}), summary(2800, {"fault": "slow_llm"}))
    assert "| response_latency_ms_p95 | 2000 | 2800 | +800 (+40%) |" in table
    assert "| task_success_rate | 0.500 | 0.500 | +0.000 (+0%) |" in table
    assert "slow_llm" in table  # the config difference is spelled out
    assert "wer" not in table  # measured on neither side


def test_cli_refuses_mixed_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for name, mode in (("a", "audio"), ("b", "text")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "summary.json").write_text(json.dumps(summary(1, {}, mode)))
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == 2
    assert "Different modes" in capsys.readouterr().err


def test_scenario_filter_rebuilds_both_summaries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = datetime(2026, 10, 11, tzinfo=UTC)
    runs = [result("barge_in_x", 1), result("happy_y", 1, success=False)]
    a = write_report(runs, mode="text", started_at=started, reports_dir=tmp_path / "a")
    b = write_report(runs, mode="text", started_at=started, reports_dir=tmp_path / "b")
    assert main([str(a), str(b), "--scenarios", "barge_in_*"]) == 0
    printed = capsys.readouterr().out
    assert "| runs | 1.000 | 1.000 |" in printed  # main applies the filter to both reports
    assert load_summary(a, "barge_in_*")["overall"]["runs"] == 1
    assert load_summary(a, None)["overall"]["runs"] == 2


def test_a_stage_timing_in_only_one_report_is_shown_not_a_crash() -> None:
    with_stages = {"overall": {}, "audio": {"agent_timing_p50_s": {"end_of_turn_delay": 0.9}}}
    without: dict[str, Any] = {"overall": {}, "audio": {"agent_timing_p50_s": {}}}
    table = compare(with_stages, without)
    assert "| agent_end_of_turn_delay_p50_s | 0.900 | n/a |" in table
