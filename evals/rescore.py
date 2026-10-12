"""`python -m evals.rescore <report>`: recompute audio metrics from a report's saved audio.

When a timing metric's definition changes, reports compared against each other have to
be scored the same way. Every audio run keeps what the caller received and its event
timeline under raw/audio/, so the metrics can be recomputed without making any calls.
Judge results and order scores are left as they are.
"""

import argparse
import json
import sys
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from evals.audio.detector import DETECTOR_SETTINGS
from evals.audio.metrics import (
    CallerUtterance,
    Timeline,
    agent_timings,
    audio_metrics,
    turn_ends_in_pauses,
)
from evals.judge.apply import attach_calibration, load_results
from evals.report import render_markdown, summarize
from evals.text_run import RunResult


def timeline_from(folder: Path) -> Timeline:
    saved: dict[str, Any] = json.loads((folder / "timeline.json").read_text())
    with wave.open(str(folder / "agent_received.wav"), "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return Timeline(
        caller=[
            CallerUtterance(
                u["text"],
                u["start"],
                u["end"],
                tuple(tuple(p) for p in u.get("pauses", [])),
                u.get("interrupt", False),
            )
            for u in saved["caller"]
        ],
        agent_audio=audio,
        agent_audio_start=saved["agent_audio_start"],
        heard_caller=[(t, text) for t, text in saved.get("heard_caller", [])],
    )


def rescore(report: Path, recordings: Path = Path("recordings")) -> tuple[list[RunResult], int]:
    """The report's runs with audio metrics recomputed, and how many had saved audio."""
    runs, done = [], 0
    for r in load_results(report):
        folder = report / "raw" / "audio" / r.session_id
        if r.audio is None or not (folder / "timeline.json").exists():
            runs.append(r)
            continue
        timeline = timeline_from(folder)
        fresh = audio_metrics(timeline)
        turns = recordings / r.session_id / "turns.jsonl"
        if turns.exists():  # the worker's own turn records, if the recording is still here
            records = [json.loads(x) for x in turns.read_text().splitlines() if x.strip()]
            fresh["agent_timing"] = agent_timings(records)
            fresh["turn_ends_in_pauses"] = turn_ends_in_pauses(timeline, records)
        runs.append(
            r.model_copy(update={"audio": r.audio | fresh | {"detector": DETECTOR_SETTINGS}})
        )
        done += 1
    return runs, done


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.rescore")
    p.add_argument("report", type=Path)
    args = p.parse_args(argv)
    summary = json.loads((args.report / "summary.json").read_text())
    runs, done = rescore(args.report)
    if not done:
        print(f"No saved audio under {args.report / 'raw' / 'audio'}.", file=sys.stderr)
        return 2
    with (args.report / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in runs:
            f.write(r.model_dump_json(exclude={"transcript"}) + "\n")
    new = summarize(
        runs,
        mode=summary["mode"],
        started_at=datetime.fromisoformat(summary["started_at"]),
        concurrency=summary.get("concurrency"),
    )
    (args.report / "summary.json").write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    (args.report / "summary.md").write_text(render_markdown(new), encoding="utf-8")
    attach_calibration(args.report)
    print(f"Rescored {done} of {len(runs)} runs from saved audio. Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
