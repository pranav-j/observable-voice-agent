"""Before/after tables for experiment and validation write-ups."""

import json
from pathlib import Path
from typing import Any

import pytest
from evals.compare import compare, main


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
