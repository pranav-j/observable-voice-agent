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


def _noise_level(audio: dict[str, Any]) -> str:
    noise = audio.get("noise")
    return "clean" if not noise else f"SNR {noise['snr_db']:g} dB"


def _audio_summary(results: list[RunResult]) -> dict[str, Any] | None:
    """Caller-side timing, recognition and cost over the runs that went through audio."""
    audio = [r.audio for r in results if r.audio is not None]
    if not audio:
        return None
    latencies = [float(x) for a in audio for x in a.get("response_latencies_ms", [])]
    stops = [float(x) for a in audio for x in a.get("barge_in_stop_ms", [])]
    dead_air = sum(a.get("dead_air_turns", 0) for a in audio)
    cutoffs = sum(a.get("false_cutoffs", 0) for a in audio)
    pauses = sum(a.get("scripted_pauses", 0) for a in audio)
    wer: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in audio:
        for key in ("all", _noise_level(a)):
            wer[key][0] += a.get("wer_errors", 0)
            wer[key][1] += a.get("wer_words", 0)
    priced = [a for a in audio if a.get("agent_cost_usd") is not None and a.get("call_seconds")]
    cost = sum(float(a["agent_cost_usd"]) for a in priced)
    minutes = sum(float(a["call_seconds"]) for a in priced) / 60
    detectors = {json.dumps(a.get("detector"), sort_keys=True) for a in audio}
    errors, words = wer.pop("all")
    return {
        "runs": len(audio),
        "measured_turns": len(latencies),
        "response_latency_ms_p50": percentile(latencies, 50),
        "response_latency_ms_p95": percentile(latencies, 95),
        "dead_air_turns": dead_air,
        "dead_air_rate": _rate(dead_air, len(latencies)),
        "barge_ins": len(stops),
        "barge_in_stop_ms_p50": percentile(stops, 50),
        "barge_in_stop_ms_p95": percentile(stops, 95),
        "scripted_pauses": pauses,
        "false_cutoffs": cutoffs,
        "false_cutoff_rate": _rate(cutoffs, pauses),
        "wer": _rate(errors, words),
        "wer_words": words,
        "wer_by_noise": {
            level: {"wer": _rate(e, n), "words": n} for level, (e, n) in sorted(wer.items())
        },
        "priced_runs": len(priced),
        "agent_cost_usd": round(cost, 4),
        "priced_minutes": round(minutes, 2),
        "cost_per_minute_usd": cost / minutes if minutes else None,
        "cost_includes_estimates": any(a.get("agent_cost_is_estimate") for a in priced),
        "hearing": sorted({str(a.get("hearing")) for a in audio}),
        # Timing depends on these; runs scored with different settings can't be compared.
        "detector": [json.loads(d) for d in sorted(detectors)],
    }


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
        "audio": _audio_summary(results),
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
    lines += _audio_markdown(summary.get("audio"))
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


def _audio_markdown(a: dict[str, Any] | None) -> list[str]:
    if a is None:
        return []
    cost = "n/a"
    if a["cost_per_minute_usd"] is not None:
        cost = (
            f"${a['cost_per_minute_usd']:.3f} (${a['agent_cost_usd']:.3f} over "
            f"{a['priced_minutes']:.1f} min, {a['priced_runs']} runs"
            f"{'; includes estimates' if a['cost_includes_estimates'] else ''})"
        )
    lines = [
        "",
        "## Audio",
        "",
        "Measured from the caller's side, from the audio it received.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Response latency p50 / p95 (ms) | {_num(a['response_latency_ms_p50'], 0)} / "
        f"{_num(a['response_latency_ms_p95'], 0)} ({a['measured_turns']} turns) |",
        f"| Dead air (over 2 s) | {a['dead_air_turns']} turns ({_pct(a['dead_air_rate'])}) |",
        f"| Barge-in stop p50 / p95 (ms) | {_num(a['barge_in_stop_ms_p50'], 0)} / "
        f"{_num(a['barge_in_stop_ms_p95'], 0)} ({a['barge_ins']} barge-ins) |",
        f"| False cut-offs | {a['false_cutoffs']}/{a['scripted_pauses']} scripted pauses "
        f"({_pct(a['false_cutoff_rate'])}) |",
        f"| WER | {_pct(a['wer'])} ({a['wer_words']} words) |",
        *(
            f"| WER, {level} | {_pct(w['wer'])} ({w['words']} words) |"
            for level, w in a["wer_by_noise"].items()
        ),
        f"| Agent cost per minute | {cost} |",
        f"| Caller hearing | {', '.join(a['hearing'])} |",
        "",
        "Detector: "
        + "; ".join(
            ", ".join(f"{k} {v}" for k, v in sorted(d.items())) if d else "unknown"
            for d in a["detector"]
        )
        + ".",
    ]
    return lines


# --- files -------------------------------------------------------------------------------


def report_dir(reports_dir: Path, *, mode: str, started_at: datetime) -> Path:
    """Create a new report directory, never reusing one."""
    out = reports_dir / f"{started_at:%Y%m%d-%H%M%S}-{mode}"
    (out / "raw").mkdir(parents=True, exist_ok=False)
    return out


def write_report(
    results: list[RunResult],
    *,
    mode: str,
    started_at: datetime,
    reports_dir: Path,
    out: Path | None = None,
) -> Path:
    """Write the report directory and return its path.

    results.jsonl and the summaries are small and meant to be committed. Full transcripts
    go under raw/, which is gitignored. Pass `out` when the directory was created up
    front, as audio runs do so they can save audio into raw/ as they go.
    """
    if out is None:
        out = report_dir(reports_dir, mode=mode, started_at=started_at)
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
