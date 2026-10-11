"""`python -m evals.gate <report>`: fail when a report is worse than the baseline.

evals/baseline.json holds the key metrics of a reviewed report, per mode. evals/gate.yaml
says how much worse each metric may get before the gate fails:

    max_drop          rates where higher is better, as an absolute drop (0.05 = 5 points)
    max_increase      timings where lower is better, as a fraction of the baseline
    max_increase_abs  rates where lower is better, as an absolute rise

A metric missing from either side (no barge-ins in the run, say) is skipped and named
in the output, never quietly passed. `--update-baseline` records a report as the new
baseline for its mode; only do that after reading the report.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

EVALS_DIR = Path(__file__).parent
BASELINE = EVALS_DIR / "baseline.json"
GATE = EVALS_DIR / "gate.yaml"

# Where each gated metric lives in summary.json.
METRICS: dict[str, tuple[str, str]] = {
    "task_success_rate": ("overall", "task_success_rate"),
    "order_exact_match_rate": ("overall", "order_exact_match_rate"),
    "response_latency_ms_p50": ("audio", "response_latency_ms_p50"),
    "response_latency_ms_p95": ("audio", "response_latency_ms_p95"),
    "barge_in_stop_ms_p95": ("audio", "barge_in_stop_ms_p95"),
    "false_cutoff_rate": ("audio", "false_cutoff_rate"),
    "wer": ("audio", "wer"),
    "cost_per_minute_usd": ("audio", "cost_per_minute_usd"),
    "error_acknowledgement_rate": ("judged", "error_acknowledgement_rate"),
    "injection_resistance_rate": ("judged", "injection_resistance_rate"),
}

Rule = Literal["max_drop", "max_increase", "max_increase_abs"]


@dataclass(frozen=True)
class Check:
    metric: str
    baseline: float | None
    current: float | None
    rule: Rule
    margin: float

    @property
    def limit(self) -> float | None:
        if self.baseline is None:
            return None
        if self.rule == "max_drop":
            return self.baseline - self.margin
        if self.rule == "max_increase":
            return self.baseline * (1 + self.margin)
        return self.baseline + self.margin

    @property
    def status(self) -> Literal["pass", "fail", "skipped"]:
        limit = self.limit
        if limit is None or self.current is None:
            return "skipped"
        worse = self.current < limit if self.rule == "max_drop" else self.current > limit
        return "fail" if worse else "pass"


def metrics_of(summary: dict[str, Any]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for name, (section, key) in METRICS.items():
        block = summary.get(section) or {}
        value = block.get(key)
        values[name] = float(value) if isinstance(value, int | float) else None
    return values


def check(summary: dict[str, Any], baseline: dict[str, Any], gate: dict[str, Any]) -> list[Check]:
    mode = summary["mode"]
    rules = gate.get(mode) or {}
    if mode not in baseline:
        raise ValueError(f"no {mode} baseline in the baseline file")
    current, base = metrics_of(summary), baseline[mode]["metrics"]
    checks = []
    for metric, rule in rules.items():
        if metric not in METRICS:
            raise ValueError(f"gate.yaml: unknown metric {metric!r}")
        ((kind, margin),) = rule.items()
        checks.append(Check(metric, base.get(metric), current[metric], kind, float(margin)))
    return checks


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def render(checks: list[Check]) -> str:
    lines = ["| Metric | Baseline | Limit | This run | Result |", "|---|---|---|---|---|"]
    for c in checks:
        lines.append(
            f"| {c.metric} | {_fmt(c.baseline)} | {_fmt(c.limit)} | {_fmt(c.current)} | "
            f"{c.status} |"
        )
    return "\n".join(lines)


def baseline_entry(summary: dict[str, Any], report: Path) -> dict[str, Any]:
    return {
        "report": report.as_posix(),
        "started_at": summary["started_at"],
        "runs": summary["overall"]["runs"],
        "metrics": metrics_of(summary),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.gate")
    p.add_argument("report", type=Path)
    p.add_argument("--baseline", type=Path, default=BASELINE)
    p.add_argument("--gate", type=Path, default=GATE)
    p.add_argument("--update-baseline", action="store_true")
    args = p.parse_args(argv)
    summary = json.loads((args.report / "summary.json").read_text())
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else {}
    if args.update_baseline:
        baseline[summary["mode"]] = baseline_entry(summary, args.report)
        args.baseline.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
        print(f"{args.baseline}: {summary['mode']} baseline is now {args.report}")
        return 0
    try:
        checks = check(summary, baseline, yaml.safe_load(args.gate.read_text()))
    except ValueError as exc:
        print(f"gate: {exc}", file=sys.stderr)
        return 2
    print(render(checks))
    failed = [c.metric for c in checks if c.status == "fail"]
    skipped = [c.metric for c in checks if c.status == "skipped"]
    if skipped:
        print(f"\nSkipped (not measured on one side): {', '.join(skipped)}")
    if failed:
        print(f"\nGate failed: {', '.join(failed)}")
        return 1
    print("\nGate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
