"""Rescoring a report's audio metrics from its saved audio, with no calls."""

import json
import wave
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from evals.report import write_report
from evals.rescore import main, rescore

from tests.evals.test_report import audio_result

RATE = 16_000


def _saved_run(root: Path, session_id: str) -> None:
    """A received track with agent speech 1.0-2.0 s and 2.4-4.0 s, and one interruption."""
    folder = root / "raw" / "audio" / session_id
    folder.mkdir(parents=True)
    audio = np.zeros(5 * RATE, dtype=np.int16)
    t = np.arange(len(audio)) / RATE
    speaking = ((t >= 1.0) & (t < 2.0)) | ((t >= 2.4) & (t < 4.0))
    audio[speaking] = (3000 * np.sin(2 * np.pi * 220 * t[speaking])).astype(np.int16)
    with wave.open(str(folder / "agent_received.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    caller = [{"text": "Wait, no.", "start": 1.5, "end": 2.2, "pauses": [], "interrupt": True}]
    (folder / "timeline.json").write_text(
        json.dumps({"agent_audio_start": 0.0, "caller": caller, "heard_caller": []})
    )


def test_rescore_recomputes_audio_metrics_from_saved_files(tmp_path: Path) -> None:
    run = audio_result(1, noise=None, barge_in_stop_ms=[500], agent_cost_usd=0.05)
    out = write_report(
        [run], mode="audio", started_at=datetime(2026, 10, 12, tzinfo=UTC), reports_dir=tmp_path
    )
    _saved_run(out, run.session_id)
    (rescored,), done = rescore(out)
    assert done == 1
    assert rescored.audio is not None
    assert rescored.audio["barge_in_stop_ms"] == [2500]  # to the end of the reply at 4.0 s
    assert rescored.audio["agent_cost_usd"] == 0.05  # everything else is kept
    assert main([str(out)]) == 0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["audio"]["barge_in_stop_ms_p50"] == 2500
