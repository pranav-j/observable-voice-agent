"""Recorded mode: score real calls against what the caller meant to order.

A real call leaves a folder in recordings/ (audio, transcript, tool calls, usage). To
score it, annotate it: evals/recorded/<session_id>.yaml says what the caller actually
wanted, written by the person who made the call. `make annotate SESSION=<id>` starts
one. The recordings stay local; the annotations are small and committed.

The order comes from Postgres, like the other modes. Timing comes from the worker's
two-channel recording, with the same detector as audio mode, so it's measured at the
agent's end of the line and leaves out the network.
"""

import json
import wave
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import yaml
from pydantic import Field, StringConstraints

from evals.audio.detector import DETECTOR_SETTINGS, speech_segments
from evals.audio.metrics import recording_metrics
from evals.scenario import Expectation, _Strict
from evals.scoring.order import score_order
from evals.text_run import RunResult, TranscriptEntry
from voice_order.prompts.loader import AGENT_SYSTEM_VERSION
from voice_order.store.base import OrderStore
from voice_order.textmode.llm import Usage

RECORDED_DIR = Path(__file__).parent / "recorded"

SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,100}$")]


class Annotation(_Strict):
    session_id: SessionId
    description: str = ""
    tags: list[str] = Field(default_factory=lambda: ["human"])
    expect: Expectation


def load_annotations(pattern: str = "*", directory: Path = RECORDED_DIR) -> list[Annotation]:
    """Annotations whose session id matches `pattern` (comma-separated globs)."""
    paths = {p for glob in pattern.split(",") for p in directory.glob(f"{glob.strip()}.yaml")}
    annotations = []
    for path in sorted(paths):
        annotation = Annotation.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if annotation.session_id != path.stem:
            raise ValueError(f"{path.name}: session_id must match the file name")
        annotations.append(annotation)
    return annotations


def _wav(path: Path) -> tuple[np.ndarray[Any, Any], int]:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def recording_timing(folder: Path) -> dict[str, Any] | None:
    """Timing metrics from the caller and agent channels, or None without them."""
    caller, agent = folder / "caller.wav", folder / "agent.wav"
    if not (caller.exists() and agent.exists()):
        return None
    caller_audio, caller_rate = _wav(caller)
    agent_audio, agent_rate = _wav(agent)
    return recording_metrics(
        speech_segments(caller_audio, caller_rate), speech_segments(agent_audio, agent_rate)
    )


def _json(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


async def score_recorded(
    annotation: Annotation, *, store: OrderStore, recordings_dir: Path
) -> RunResult:
    folder = recordings_dir / annotation.session_id
    usage: dict[str, Any] = _json(folder / "usage.json") or {}
    config: dict[str, Any] | None = _json(folder / "config.json")
    rows: list[dict[str, Any]] = _json(folder / "transcript.json") or []
    timing = recording_timing(folder)
    error = None
    if not folder.is_dir():
        error = f"no recording folder {folder}"
    elif timing is None:
        error = "the recording has no caller.wav and agent.wav"
    final = await store.get(annotation.session_id)
    llm = [m for m in usage.get("models", []) if m.get("kind") == "llm"]
    escalated = final is not None and final.status == "escalated"
    return RunResult(
        scenario_id=annotation.session_id,
        tags=annotation.tags,
        run=1,
        session_id=annotation.session_id,
        mode="recorded",
        end_reason="error" if error else ("transferred" if escalated else "recorded_call"),
        error=error,
        turns=sum(r.get("role") == "user" for r in rows),
        duration_s=float(usage.get("duration_seconds") or 0.0),
        score=score_order(final, annotation.expect),
        agent_usage=Usage(
            sum(m.get("input_tokens", 0) for m in llm),
            sum(m.get("output_tokens", 0) for m in llm),
        ),
        caller_usage=Usage(),
        tool_limit_hits=0,
        skipped_behaviors=[],
        agent_model=(config or {}).get("llm_model", "unknown"),
        caller_model="human",
        agent_prompt_version=(config or {}).get("agent_prompt_version", AGENT_SYSTEM_VERSION),
        caller_prompt_version="human",
        transcript=[
            TranscriptEntry(speaker="caller" if r["role"] == "user" else "agent", text=r["text"])
            for r in rows
        ],
        audio=None
        if timing is None
        else timing
        | {
            "hearing": "human",
            "noise": None,
            "agent_cost_usd": usage.get("total_cost_usd"),
            "agent_cost_is_estimate": any(
                m.get("estimated_from_call_length") for m in usage.get("models", [])
            ),
            "call_seconds": usage.get("duration_seconds"),
            "detector": DETECTOR_SETTINGS,
            "agent_config": config,
        },
    )
