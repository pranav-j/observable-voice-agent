"""`python -m evals.compare <before> <after>`: two reports' key metrics side by side.

For before/after write-ups (latency changes, seeded faults), so every number in them
comes straight from report files. Also notes when the two runs differ in what they ran.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.gate import metrics_of

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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.compare")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    args = p.parse_args(argv)
    before, after = (
        json.loads((r / "summary.json").read_text()) for r in (args.before, args.after)
    )
    if before["mode"] != after["mode"]:
        print(f"Different modes: {before['mode']} vs {after['mode']}.", file=sys.stderr)
        return 2
    print(f"Before: {args.before}\nAfter: {args.after}\n")
    print(compare(before, after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
