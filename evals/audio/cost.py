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


def past_call_costs(
    recordings_dir: Path, providers: tuple[str, str] = ("openai", "openai")
) -> list[float]:
    """Agent cost in USD of earlier audio eval calls with the same speech providers.

    Local speech costs next to nothing, so mixing calls made with hosted and local speech
    would make the estimate meaningless. Calls saved before the settings were recorded
    all used hosted speech.
    """
    costs = []
    for path in sorted(recordings_dir.glob("audio-*/usage.json")):
        try:
            cost = json.loads(path.read_text()).get("total_cost_usd")
            config_file = path.parent / "config.json"
            config = json.loads(config_file.read_text()) if config_file.exists() else {}
        except (OSError, ValueError):
            continue
        used = (config.get("stt_provider", "openai"), config.get("tts_provider", "openai"))
        if used == providers and isinstance(cost, int | float) and cost > 0:
            costs.append(float(cost))
    return costs


def estimate(runs: int, past: list[float], caller_speech_paid: bool = True) -> Estimate:
    if not past:
        return Estimate(None, "no earlier audio calls to estimate from")
    per_call = median(past)
    return Estimate(
        runs * per_call,
        f"median agent cost of {len(past)} earlier audio calls like these, ${per_call:.3f} each; "
        + (
            "the simulated caller's speech and LLM calls cost extra"
            if caller_speech_paid
            else "the simulated caller's LLM calls cost extra"
        ),
    )
