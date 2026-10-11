"""Turn run results into summary.json, summary.md and the report directory."""

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from evals.text_run import RunResult


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it.

    Defined here once so the number means the same thing in every report.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _mean(values: list[float]) -> float | None:
    return fmean(values) if values else None


def summarize(results: list[RunResult], *, mode: str, started_at: datetime) -> dict[str, Any]:
    by_scenario: dict[str, list[RunResult]] = defaultdict(list)
    by_tag: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by_scenario[r.scenario_id].append(r)
        for tag in r.tags:
            by_tag[tag].append(r)

    scenarios: dict[str, dict[str, Any]] = {}
    for sid, runs in sorted(by_scenario.items()):
        successes = sum(r.score.task_success for r in runs)
        scenarios[sid] = {
            "tags": runs[0].tags,
            "runs": len(runs),
            "successes": successes,
            "pass_rate": _rate(successes, len(runs)),
            "passed_all": successes == len(runs),
            "errors": sum(r.end_reason == "error" for r in runs),
            "mean_field_accuracy": _mean(
                [r.score.field_accuracy for r in runs if r.score.field_accuracy is not None]
            ),
            "end_reasons": dict(sorted(Counter(r.end_reason for r in runs).items())),
        }

    scored = [r for r in results if r.score.exact_match is not None]
    successes = sum(r.score.task_success for r in results)
    passing_all = sum(s["passed_all"] for s in scenarios.values())
    turns = [float(r.turns) for r in results]
    durations = [r.duration_s for r in results]
    overall = {
        "runs": len(results),
        "scenarios": len(scenarios),
        "task_successes": successes,
        "task_success_rate": _rate(successes, len(results)),
        "scenarios_passing_all_runs": passing_all,
        "scenarios_passing_all_runs_rate": _rate(passing_all, len(scenarios)),
        "order_exact_match_runs": len(scored),
        "order_exact_match_rate": _rate(
            sum(bool(r.score.exact_match) for r in scored), len(scored)
        ),
        "mean_field_accuracy": _mean(
            [r.score.field_accuracy for r in scored if r.score.field_accuracy is not None]
        ),
        "escalations": sum(r.score.escalated for r in results),
        "expected_escalations": sum(r.score.expected_escalation for r in results),
        "escalation_agreement_rate": _rate(
            sum(r.score.escalated == r.score.expected_escalation for r in results), len(results)
        ),
        "errors": sum(r.end_reason == "error" for r in results),
        "caller_hung_up_early": sum(r.end_reason == "caller_hung_up_early" for r in results),
        "tool_limit_hits": sum(r.tool_limit_hits for r in results),
        "confirmed_before_reply_runs": sum(r.confirmed_before_reply > 0 for r in results),
        "skipped_audio_behaviors": sum(len(r.skipped_behaviors) for r in results),
        "turns_p50": percentile(turns, 50),
        "turns_p95": percentile(turns, 95),
        "duration_s_p50": percentile(durations, 50),
        "duration_s_p95": percentile(durations, 95),
        "agent_tokens": {
            "input": sum(r.agent_usage.input_tokens for r in results),
            "output": sum(r.agent_usage.output_tokens for r in results),
        },
        "caller_tokens": {
            "input": sum(r.caller_usage.input_tokens for r in results),
            "output": sum(r.caller_usage.output_tokens for r in results),
        },
    }
    tags = {
        tag: {
            "runs": len(runs),
            "successes": sum(r.score.task_success for r in runs),
            "pass_rate": _rate(sum(r.score.task_success for r in runs), len(runs)),
        }
        for tag, runs in sorted(by_tag.items())
    }
    failures = [
        {
            "scenario_id": r.scenario_id,
            "run": r.run,
            "session_id": r.session_id,
            "end_reason": r.end_reason,
            "error": r.error,
            "mismatches": list(r.score.mismatches),
        }
        for r in sorted(results, key=lambda r: (r.scenario_id, r.run))
        if not r.score.task_success
    ]
    violations = [
        {
            "scenario_id": r.scenario_id,
            "run": r.run,
            "session_id": r.session_id,
            "confirmed_before_reply": r.confirmed_before_reply,
        }
        for r in sorted(results, key=lambda r: (r.scenario_id, r.run))
        if r.confirmed_before_reply
    ]
    return {
        "mode": mode,
        "started_at": started_at.isoformat(timespec="seconds"),
        "agent_models": sorted({r.agent_model for r in results}),
        "caller_models": sorted({r.caller_model for r in results}),
        "agent_prompt_versions": sorted({r.agent_prompt_version for r in results}),
        "caller_prompt_versions": sorted({r.caller_prompt_version for r in results}),
        "overall": overall,
        "by_tag": tags,
        "scenarios": scenarios,
        "failures": failures,
        "rule_violations": violations,
    }


# --- markdown ----------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(summary: dict[str, Any]) -> str:
    o = summary["overall"]
    lines = [
        f"# Eval report: {summary['mode']} mode",
        "",
        f"Started {summary['started_at']}. "
        f"Agent {', '.join(summary['agent_models'])} "
        f"(prompt {', '.join(summary['agent_prompt_versions'])}), "
        f"caller {', '.join(summary['caller_models'])} "
        f"(prompt {', '.join(summary['caller_prompt_versions'])}).",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Task success | {_pct(o['task_success_rate'])} "
        f"({o['task_successes']}/{o['runs']} runs) |",
        f"| Scenarios passing all runs | {o['scenarios_passing_all_runs']}/{o['scenarios']} "
        f"({_pct(o['scenarios_passing_all_runs_rate'])}) |",
        f"| Order exact match | {_pct(o['order_exact_match_rate'])} "
        f"(of {o['order_exact_match_runs']} scored runs) |",
        f"| Mean field accuracy | {_num(o['mean_field_accuracy'])} |",
        f"| Escalation agreement | {_pct(o['escalation_agreement_rate'])} "
        f"({o['escalations']} escalated, {o['expected_escalations']} expected) |",
        f"| Errors | {o['errors']} |",
        f"| Caller hung up mid-order | {o['caller_hung_up_early']} runs |",
        f"| Tool-round limit hits | {o['tool_limit_hits']} |",
        f"| Confirmed before the caller replied | {o['confirmed_before_reply_runs']} runs |",
        f"| Turns p50 / p95 | {_num(o['turns_p50'], 0)} / {_num(o['turns_p95'], 0)} |",
        f"| Run duration p50 / p95 (s) | {_num(o['duration_s_p50'], 1)} / "
        f"{_num(o['duration_s_p95'], 1)} |",
        f"| Agent tokens in / out | {o['agent_tokens']['input']:,} / "
        f"{o['agent_tokens']['output']:,} |",
        f"| Caller tokens in / out | {o['caller_tokens']['input']:,} / "
        f"{o['caller_tokens']['output']:,} |",
        "",
        "## By tag",
        "",
        "| Tag | Pass |",
        "|---|---|",
        *(
            f"| {tag} | {t['successes']}/{t['runs']} ({_pct(t['pass_rate'])}) |"
            for tag, t in summary["by_tag"].items()
        ),
        "",
        "## By scenario",
        "",
        "| Scenario | Tags | Pass | Field accuracy | End reasons |",
        "|---|---|---|---|---|",
    ]
    for sid, s in summary["scenarios"].items():
        reasons = ", ".join(f"{k} x{v}" for k, v in s["end_reasons"].items())
        lines.append(
            f"| {sid} | {', '.join(s['tags'])} | {s['successes']}/{s['runs']} | "
            f"{_num(s['mean_field_accuracy'])} | {reasons} |"
        )
    lines += ["", "## Failures", ""]
    if not summary["failures"]:
        lines.append("None.")
    for f in summary["failures"]:
        detail = f["error"] or "; ".join(f["mismatches"]) or "no mismatches recorded"
        lines.append(f"- **{f['scenario_id']}** run {f['run']} ({f['end_reason']}): {detail}")
    lines += ["", "## Rule violations", ""]
    if not summary["rule_violations"]:
        lines.append("None.")
    for v in summary["rule_violations"]:
        lines.append(
            f"- **{v['scenario_id']}** run {v['run']}: confirmed in the same turn as the "
            f"read-back, before the caller replied (x{v['confirmed_before_reply']})"
        )
    return "\n".join(lines) + "\n"


# --- files -------------------------------------------------------------------------------


def write_report(
    results: list[RunResult], *, mode: str, started_at: datetime, reports_dir: Path
) -> Path:
    """Write the report directory and return its path.

    results.jsonl and the summaries are small and meant to be committed. Full transcripts
    go under raw/, which is gitignored.
    """
    out = reports_dir / f"{started_at:%Y%m%d-%H%M%S}-{mode}"
    (out / "raw").mkdir(parents=True, exist_ok=False)
    ordered = sorted(results, key=lambda r: (r.scenario_id, r.run))
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in ordered:
            f.write(r.model_dump_json(exclude={"transcript"}) + "\n")
    with (out / "raw" / "transcripts.jsonl").open("w", encoding="utf-8") as f:
        for r in ordered:
            f.write(
                r.model_dump_json(include={"scenario_id", "run", "session_id", "transcript"}) + "\n"
            )
    summary = summarize(results, mode=mode, started_at=started_at)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
    return out
