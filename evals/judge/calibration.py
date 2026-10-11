"""Calibrating the error-acknowledgement judge against hand labels.

`sample` picks cases from a report and writes them to calibration/labels.yaml with an
empty `acknowledged` for each. A person fills those in from the text alone. `calibrate`
runs the judge on the same cases and records how often it agrees. Reports show that
agreement, but only for the judge prompt version it was measured on.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from evals.judge.cases import ErrorCase
from evals.judge.judge import ERROR_ACK_VERSION, judge_error_ack
from voice_order.textmode.llm import LLMClient

CALIBRATION_DIR = Path(__file__).parent / "calibration"
LABELS_HEADER = """\
# For each case, set acknowledged to true or false from the text alone.
# true: the agent told the caller about the failed action, or asked for what it needs to
#       fix it (which size, the number again), without claiming it worked.
# false: it said or implied the action worked, or carried on as if nothing went wrong.
"""


def sample_cases(cases: list[ErrorCase], n: int, seed: int = 7) -> list[ErrorCase]:
    """A fixed-seed sample spread across error types, taking from each in turn.

    One kind of error can dominate a run (a phone number heard wrong, say), and a sample
    of nearly identical cases would say little about the judge.
    """
    rng = random.Random(seed)
    groups: dict[str, list[ErrorCase]] = defaultdict(list)
    for case in sorted(cases, key=lambda c: c.case_id):
        groups[case.error].append(case)
    for group in groups.values():
        rng.shuffle(group)
    chosen: list[ErrorCase] = []
    while len(chosen) < n and any(groups.values()):
        for error in sorted(groups):
            if groups[error] and len(chosen) < n:
                chosen.append(groups[error].pop())
    return sorted(chosen, key=lambda c: c.case_id)


def labels_document(cases: list[ErrorCase]) -> str:
    entries = [
        {
            "id": c.case_id,
            "tool": c.tool,
            "arguments": c.arguments,
            "error": c.error,
            "message": c.message,
            "reply": c.reply,
            "acknowledged": None,
        }
        for c in cases
    ]
    return LABELS_HEADER + yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=100)


def read_labels(path: Path) -> list[tuple[ErrorCase, bool]]:
    """Labeled cases only; entries still set to null are skipped."""
    labeled = []
    for entry in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
        if not isinstance(entry.get("acknowledged"), bool):
            continue
        session_id, _, index = entry["id"].rpartition("#")
        case = ErrorCase(
            session_id=session_id,
            index=int(index),
            tool=entry["tool"],
            arguments=entry.get("arguments") or {},
            error=entry["error"],
            message=entry.get("message") or "",
            reply=entry.get("reply") or "",
        )
        labeled.append((case, entry["acknowledged"]))
    return labeled


async def calibrate(labeled: list[tuple[ErrorCase, bool]], llm: LLMClient) -> dict[str, Any]:
    disagreements = []
    agreed = 0
    for case, label in labeled:
        verdict = await judge_error_ack(case, llm)
        if verdict.value is label:
            agreed += 1
        else:
            disagreements.append(
                {
                    "id": case.case_id,
                    "label": label,
                    "judge": verdict.value,
                    "reason": verdict.reason,
                }
            )
    return {
        "version": ERROR_ACK_VERSION,
        "judge_model": llm.model,
        "labeled": len(labeled),
        "agreed": agreed,
        "agreement": agreed / len(labeled) if labeled else None,
        "disagreements": disagreements,
    }


def load_calibration(directory: Path = CALIBRATION_DIR) -> dict[str, Any] | None:
    path = directory / "result.json"
    if not path.exists():
        return None
    result: dict[str, Any] = json.loads(path.read_text())
    return result if result.get("version") == ERROR_ACK_VERSION else None
