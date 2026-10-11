"""`python -m evals.compare <before> <after>`: two reports' key metrics side by side.

For before/after write-ups (latency changes, seeded faults), so every number in them
comes straight from report files. Also notes when the two runs differ in what they ran.
"""

import argparse
import json
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from evals.gate import metrics_of
from evals.judge.apply import load_results
from evals.report import summarize

EXTRA: dict[str, tuple[str, str]] = {
    "runs": ("overall", "runs"),
    "dead_air_rate": ("audio", "dead_air_rate"),
    "barge_in_stop_ms_p50": ("audio", "barge_in_stop_ms_p50"),
    "doubled_replies": ("audio", "doubled_replies"),
}


def _metrics(summary: dict[str, Any]) -> dict[str, float | None]:
    values = metrics_of(summary)
    for name, (section, key) in EXTRA.items():
        value = (summary.get(section) or {}).get(key)
        values[name] = float(value) if isinstance(value, int | float) else None
    return values


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}" if abs(value) < 10 else f"{value:.0f}"


def _delta(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return ""
    diff = after - before
    rel = f" ({diff / before:+.0%})" if before else ""
    return f"{diff:+.3f}{rel}" if abs(diff) < 10 else f"{diff:+.0f}{rel}"


def compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    b, a = _metrics(before), _metrics(after)
    lines = ["| Metric | Before | After | Change |", "|---|---|---|---|"]
    for name in b:
        if b[name] is None and a[name] is None:
            continue
        lines.append(f"| {name} | {_fmt(b[name])} | {_fmt(a[name])} | {_delta(b[name], a[name])} |")
    configs = [(s.get("audio") or {}).get("agent_configs") for s in (before, after)]
    if configs[0] != configs[1]:
        lines += ["", f"Agent config before: {configs[0]}", f"Agent config after: {configs[1]}"]
    return "\n".join(lines)


def load_summary(report: Path, scenarios: str | None) -> dict[str, Any]:
    """The report's summary, or one rebuilt from only the runs matching `scenarios`."""
    summary: dict[str, Any] = json.loads((report / "summary.json").read_text())
    if scenarios is None:
        return summary
    globs = [g.strip() for g in scenarios.split(",")]
    runs = [r for r in load_results(report) if any(fnmatch(r.scenario_id, g) for g in globs)]
    return summarize(
        runs,
        mode=summary["mode"],
        started_at=datetime.fromisoformat(summary["started_at"]),
        concurrency=summary.get("concurrency"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.compare")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--scenarios", help="compare only these scenarios (comma-separated globs)")
    args = p.parse_args(argv)
    before, after = (load_summary(r, args.scenarios) for r in (args.before, args.after))
    if before["mode"] != after["mode"]:
        print(f"Different modes: {before['mode']} vs {after['mode']}.", file=sys.stderr)
        return 2
    print(f"Before: {args.before}\nAfter: {args.after}\n")
    print(compare(before, after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
