"""Report aggregation and files, from hand-built run results."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from evals.report import percentile, render_markdown, report_dir, summarize, write_report
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
    confirmed_before_reply: int = 0,
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
        "confirmed_before_reply": confirmed_before_reply,
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


def test_rule_violations_are_counted_and_listed() -> None:
    results = [result("a", 1, confirmed_before_reply=2), result("a", 2), result("b", 1)]
    summary = summarize(results, mode="text", started_at=STARTED)
    assert summary["overall"]["confirmed_before_reply_runs"] == 1
    assert [(v["scenario_id"], v["run"]) for v in summary["rule_violations"]] == [("a", 1)]
    md = render_markdown(summary)
    assert "| Confirmed before the caller replied | 1 runs |" in md
    assert "- **a** run 1: confirmed in the same turn as the read-back" in md


def test_no_rule_violations() -> None:
    md = render_markdown(summarize([result("a", 1)], mode="text", started_at=STARTED))
    assert md.endswith("## Rule violations\n\nNone.\n")


def test_old_results_without_the_field_still_load() -> None:
    row = json.loads(result("a", 1).model_dump_json(exclude={"transcript"}))
    del row["confirmed_before_reply"]
    assert RunResult.model_validate(row).confirmed_before_reply == 0


def test_early_hang_ups_are_counted() -> None:
    results = [result("a", 1, success=False, end_reason="caller_hung_up_early"), result("a", 2)]
    summary = summarize(results, mode="text", started_at=STARTED)
    assert summary["overall"]["caller_hung_up_early"] == 1
    assert "| Caller hung up mid-order | 1 runs |" in render_markdown(summary)


DETECTOR = {"threshold_dbfs": -45, "frame_ms": 10}


def audio_result(run: int, *, noise: dict[str, Any] | None, **audio: Any) -> RunResult:
    r = result("happy_path_single_coffee", run)
    metrics = {
        "response_latencies_ms": [],
        "dead_air_turns": 0,
        "barge_in_stop_ms": [],
        "false_cutoffs": 0,
        "scripted_pauses": 0,
        "wer_errors": 0,
        "wer_words": 0,
        "hearing": "transcript",
        "noise": noise,
        "agent_cost_usd": None,
        "agent_cost_is_estimate": False,
        "call_seconds": 60.0,
        "detector": DETECTOR,
        "agent_config": {"eou_silence_ms": 500},
    }
    return r.model_copy(update={"mode": "audio", "audio": metrics | audio})


def test_text_reports_have_no_audio_section(results: list[RunResult]) -> None:
    summary = summarize(results, mode="text", started_at=STARTED)
    assert summary["audio"] is None
    assert "## Audio" not in render_markdown(summary)


def test_audio_aggregates() -> None:
    cafe = {"clip": "cafe", "snr_db": 10}
    runs = [
        audio_result(
            1,
            noise=None,
            response_latencies_ms=[800, 1200, 2500],
            dead_air_turns=1,
            wer_errors=1,
            wer_words=20,
            agent_cost_usd=0.06,
            call_seconds=90.0,
        ),
        audio_result(
            2,
            noise=cafe,
            response_latencies_ms=[900],
            barge_in_stop_ms=[300, 500],
            false_cutoffs=1,
            scripted_pauses=2,
            wer_errors=3,
            wer_words=10,
            agent_cost_usd=0.04,
            agent_cost_is_estimate=True,
            call_seconds=30.0,
        ),
        audio_result(3, noise=cafe),  # no usage file: left out of cost
    ]
    a = summarize(runs, mode="audio", started_at=STARTED)["audio"]
    assert a["runs"] == 3
    assert (a["response_latency_ms_p50"], a["response_latency_ms_p95"]) == (900, 2500)
    assert (a["dead_air_turns"], a["dead_air_rate"]) == (1, 0.25)
    assert (a["barge_in_stop_ms_p50"], a["barge_in_stop_ms_p95"]) == (300, 500)
    assert a["false_cutoff_rate"] == 0.5
    assert a["wer"] == 4 / 30
    assert a["wer_by_noise"] == {
        "SNR 10 dB": {"wer": 0.3, "words": 10},
        "clean": {"wer": 0.05, "words": 20},
    }
    assert a["priced_runs"] == 2
    assert a["cost_per_minute_usd"] == pytest.approx(0.05)
    assert a["cost_includes_estimates"] is True
    assert a["detector"] == [DETECTOR]


def test_audio_markdown_shows_metrics_and_detector() -> None:
    runs = [audio_result(1, noise=None, response_latencies_ms=[1000], wer_words=5)]
    md = render_markdown(summarize(runs, mode="audio", started_at=STARTED))
    assert "## Audio" in md
    assert "| Response latency p50 / p95 (ms) | 1000 / 1000 (1 turns) |" in md
    assert "| Agent cost per minute | n/a |" in md
    assert "Detector: frame_ms 10, threshold_dbfs -45." in md
    assert "Agent config: eou_silence_ms 500." in md


def test_mixed_agent_configs_are_all_listed() -> None:
    a = audio_result(1, noise=None)
    b = audio_result(2, noise=None, agent_config={"eou_silence_ms": 150})
    configs = summarize([a, b], mode="audio", started_at=STARTED)["audio"]["agent_configs"]
    assert configs == [{"eou_silence_ms": 150}, {"eou_silence_ms": 500}]


def test_concurrency_is_recorded() -> None:
    summary = summarize([result("x", 1)], mode="audio", started_at=STARTED, concurrency=2)
    assert summary["concurrency"] == 2
    assert "2 calls at a time." in render_markdown(summary)


def test_audio_report_dir_can_be_created_first(tmp_path: Path) -> None:
    out = report_dir(tmp_path, mode="audio", started_at=STARTED)
    (out / "raw" / "audio").mkdir()
    runs = [audio_result(1, noise=None)]
    written = write_report(runs, mode="audio", started_at=STARTED, reports_dir=tmp_path, out=out)
    assert written == out
    assert (out / "summary.md").exists()
    assert (out / "raw" / "audio").is_dir()
