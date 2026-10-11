"""Report aggregation and files, from hand-built run results."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from evals.report import percentile, render_markdown, summarize, write_report
from evals.scoring.order import OrderScore
from evals.text_run import RunResult, TranscriptEntry

from voice_order.textmode.llm import Usage

STARTED = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)


def result(
    scenario_id: str,
    run: int,
    *,
    success: bool = True,
    exact: bool | None = True,
    accuracy: float | None = 1.0,
    tags: list[str] | None = None,
    end_reason: str = "caller_ended",
    error: str | None = None,
    escalated: bool = False,
    expected_escalation: bool = False,
    turns: int = 5,
    duration_s: float = 10.0,
    mismatches: tuple[str, ...] = (),
) -> RunResult:
    fields: dict[str, Any] = {
        "scenario_id": scenario_id,
        "tags": tags or ["happy_path"],
        "run": run,
        "session_id": f"eval-{scenario_id}-r{run}",
        "end_reason": end_reason,
        "error": error,
        "turns": turns,
        "duration_s": duration_s,
        "score": OrderScore(
            status="confirmed" if success else "abandoned",
            expected_status="confirmed",
            exact_match=exact,
            field_accuracy=accuracy,
            task_success=success,
            escalated=escalated,
            expected_escalation=expected_escalation,
            mismatches=mismatches,
        ),
        "agent_usage": Usage(1000, 50),
        "caller_usage": Usage(300, 20),
        "tool_limit_hits": 0,
        "skipped_behaviors": [],
        "agent_model": "gpt-6-luna",
        "caller_model": "gpt-6-luna",
        "agent_prompt_version": "v1",
        "caller_prompt_version": "v1",
        "transcript": [TranscriptEntry(speaker="agent", text="Hi")],
    }
    return RunResult(**fields)


@pytest.mark.parametrize(
    ("values", "p", "expected"),
    [
        (list(range(1, 11)), 50, 5),
        (list(range(1, 11)), 95, 10),
        (list(range(1, 11)), 90, 9),
        ([7.0], 95, 7.0),
        ([3, 1, 2], 50, 2),
        ([], 50, None),
    ],
)
def test_nearest_rank_percentile(values: list[float], p: float, expected: float | None) -> None:
    assert percentile(values, p) == expected


@pytest.fixture
def results() -> list[RunResult]:
    return [
        result("a_happy", 1, turns=4, duration_s=8.0),
        result("a_happy", 2, turns=6, duration_s=12.0),
        result(
            "b_correction",
            1,
            success=False,
            exact=False,
            accuracy=0.75,
            tags=["correction"],
            mismatches=("missing: 1x cold_coffee (medium)",),
        ),
        result("b_correction", 2, tags=["correction"]),
        result(
            "c_human",
            1,
            exact=None,
            accuracy=None,
            tags=["human"],
            end_reason="transferred",
            escalated=True,
            expected_escalation=True,
        ),
        result(
            "d_flaky",
            1,
            success=False,
            exact=False,
            accuracy=0.0,
            end_reason="error",
            error="RuntimeError: API is down",
        ),
    ]


def test_overall_numbers(results: list[RunResult]) -> None:
    o = summarize(results, mode="text", started_at=STARTED)["overall"]
    assert (o["runs"], o["scenarios"], o["task_successes"]) == (6, 4, 4)
    assert o["task_success_rate"] == pytest.approx(4 / 6)  # the error run counts as a failure
    assert (o["scenarios_passing_all_runs"], o["scenarios"]) == (2, 4)  # a_happy and c_human
    # exact match is only over runs that score the order's contents (c_human doesn't)
    assert o["order_exact_match_runs"] == 5
    assert o["order_exact_match_rate"] == pytest.approx(3 / 5)
    assert o["mean_field_accuracy"] == pytest.approx((1 + 1 + 0.75 + 1 + 0) / 5)
    assert o["escalation_agreement_rate"] == 1.0
    assert (o["escalations"], o["expected_escalations"]) == (1, 1)
    assert o["errors"] == 1
    assert (o["turns_p50"], o["turns_p95"]) == (5, 6)
    assert o["agent_tokens"] == {"input": 6000, "output": 300}
    assert o["caller_tokens"] == {"input": 1800, "output": 120}


def test_per_scenario_and_tag(results: list[RunResult]) -> None:
    s = summarize(results, mode="text", started_at=STARTED)
    b = s["scenarios"]["b_correction"]
    assert (b["runs"], b["successes"], b["passed_all"]) == (2, 1, False)
    assert b["mean_field_accuracy"] == pytest.approx(0.875)
    assert s["scenarios"]["c_human"]["end_reasons"] == {"transferred": 1}
    assert s["by_tag"]["correction"] == {"runs": 2, "successes": 1, "pass_rate": 0.5}
    assert list(s["scenarios"]) == ["a_happy", "b_correction", "c_human", "d_flaky"]


def test_failures_list_mismatches_and_errors(results: list[RunResult]) -> None:
    failures = summarize(results, mode="text", started_at=STARTED)["failures"]
    assert [(f["scenario_id"], f["run"]) for f in failures] == [("b_correction", 1), ("d_flaky", 1)]
    assert failures[0]["mismatches"] == ["missing: 1x cold_coffee (medium)"]
    assert failures[1]["error"] == "RuntimeError: API is down"


def test_markdown(results: list[RunResult]) -> None:
    md = render_markdown(summarize(results, mode="text", started_at=STARTED))
    assert md.startswith("# Eval report: text mode\n")
    assert "| Task success | 66.7% (4/6 runs) |" in md
    assert "| Scenarios passing all runs | 2/4 (50.0%) |" in md
    assert "| b_correction | correction | 1/2 | 0.88 | caller_ended x2 |" in md
    assert "- **b_correction** run 1 (caller_ended): missing: 1x cold_coffee (medium)" in md
    assert "- **d_flaky** run 1 (error): RuntimeError: API is down" in md


def test_markdown_with_no_failures() -> None:
    md = render_markdown(summarize([result("a", 1)], mode="text", started_at=STARTED))
    assert "## Failures\n\nNone.\n" in md


def test_write_report(results: list[RunResult], tmp_path: Path) -> None:
    out = write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
    assert out == tmp_path / "20261011-120000-text"
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 6
    assert "transcript" not in rows[0]  # transcripts are bulky; they live under raw/
    raw = [
        json.loads(line) for line in (out / "raw" / "transcripts.jsonl").read_text().splitlines()
    ]
    assert raw[0]["transcript"] == [
        {"speaker": "agent", "text": "Hi", "tool_calls": [], "scripted": False}
    ]
    assert json.loads((out / "summary.json").read_text())["overall"]["runs"] == 6
    assert (out / "summary.md").read_text().startswith("# Eval report")


def test_results_file_alone_can_rebuild_the_summary(
    results: list[RunResult], tmp_path: Path
) -> None:
    out = write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
    reloaded = [
        RunResult.model_validate_json(line)
        for line in (out / "results.jsonl").read_text().splitlines()
    ]
    original = summarize(results, mode="text", started_at=STARTED)
    assert summarize(reloaded, mode="text", started_at=STARTED) == original


def test_report_dirs_are_never_overwritten(results: list[RunResult], tmp_path: Path) -> None:
    write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
    with pytest.raises(FileExistsError):
        write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
