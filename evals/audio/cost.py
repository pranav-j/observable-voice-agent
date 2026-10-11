"""What an audio eval run is likely to cost, before it starts.

Audio runs are real calls billed by the minute, so the runner prints an estimate and
asks for --yes above a small threshold. The estimate comes from what earlier audio calls
actually cost the agent (the usage.json the worker saves per call), not from guessed
per-minute figures. Caller-side text-to-speech and LLM calls come on top.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

YES_ABOVE_USD = 1.00  # estimates above this need --yes
YES_ABOVE_RUNS_UNKNOWN = 3  # with no history to estimate from, more runs than this need --yes


@dataclass(frozen=True)
class Estimate:
    usd: float | None  # None when there are no earlier audio calls to go on
    basis: str

    def needs_yes(self, runs: int) -> bool:
        if self.usd is None:
            return runs > YES_ABOVE_RUNS_UNKNOWN
        return self.usd > YES_ABOVE_USD


def past_call_costs(recordings_dir: Path) -> list[float]:
    """Agent cost in USD of each earlier audio eval call that has a priced usage file."""
    costs = []
    for path in sorted(recordings_dir.glob("audio-*/usage.json")):
        try:
            cost = json.loads(path.read_text()).get("total_cost_usd")
        except (OSError, ValueError):
            continue
        if isinstance(cost, int | float) and cost > 0:
            costs.append(float(cost))
    return costs


def estimate(runs: int, past: list[float]) -> Estimate:
    if not past:
        return Estimate(None, "no earlier audio calls to estimate from")
    per_call = median(past)
    return Estimate(
        runs * per_call,
        f"median agent cost of {len(past)} earlier audio calls, ${per_call:.3f} each; "
        "the simulated caller's speech and LLM calls cost extra",
    )
