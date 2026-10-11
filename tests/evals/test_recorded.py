"""Recorded mode: annotations, timing from a two-channel recording, and scoring."""

import json
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml
from evals.annotate import draft
from evals.recorded import Annotation, load_annotations, recording_timing, score_recorded
from pydantic import ValidationError

from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.base import InMemoryOrderStore

RATE = 48_000
SESSION = "call-20261012-101500-ab12cd"
EXPECT = {
    "status": "confirmed",
    "order": {
        "items": [{"item": "masala_dosa", "quantity": 2, "modifiers": []}],
        "customer": {"name": "Anil", "phone": "9000012345"},
    },
}


def _write_wav(path: Path, speech: list[tuple[float, float]], seconds: float = 5.0) -> None:
    """A tone loud enough for the detector during each (start, end), silence elsewhere."""
    audio = np.zeros(int(seconds * RATE), dtype=np.int16)
    t = np.arange(len(audio)) / RATE
    for start, end in speech:
        on = (t >= start) & (t < end)
        audio[on] = (3000 * np.sin(2 * np.pi * 220 * t[on])).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())


def _recording(root: Path) -> Path:
    """A finished call as the worker leaves it: caller 0.5-1.5 s, agent 2.0-3.0 s."""
    folder = root / SESSION
    folder.mkdir(parents=True)
    _write_wav(folder / "caller.wav", [(0.5, 1.5)])
    _write_wav(folder / "agent.wav", [(2.0, 3.0)])
    (folder / "usage.json").write_text(
        json.dumps({"total_cost_usd": 0.02, "duration_seconds": 60.0, "models": []})
    )
    (folder / "config.json").write_text(
        json.dumps({"llm_model": "gpt-6-luna", "agent_prompt_version": "v1"})
    )
    (folder / "transcript.json").write_text(
        json.dumps(
            [
                {"role": "assistant", "text": "Hi, what would you like?"},
                {"role": "user", "text": "Two masala dosas."},
            ]
        )
    )
    return folder


def _annotation_file(directory: Path, session_id: str = SESSION, **extra: object) -> Path:
    path = directory / f"{session_id}.yaml"
    path.write_text(yaml.safe_dump({"session_id": session_id, "expect": EXPECT, **extra}))
    return path


def test_annotations_load_by_glob(tmp_path: Path) -> None:
    _annotation_file(tmp_path)
    _annotation_file(tmp_path, "call-other")
    assert [a.session_id for a in load_annotations("call-2026*", tmp_path)] == [SESSION]
    assert load_annotations("*", tmp_path)[0].tags == ["human"]


def test_annotation_must_match_its_file_name(tmp_path: Path) -> None:
    (tmp_path / "wrong.yaml").write_text(yaml.safe_dump({"session_id": SESSION, "expect": EXPECT}))
    with pytest.raises(ValueError, match="must match the file name"):
        load_annotations("*", tmp_path)


def test_annotation_phone_numbers_stay_fake() -> None:
    items = [{"item": "masala_dosa", "quantity": 2}]
    real_looking = {
        "status": "confirmed",
        "order": {"items": items, "customer": {"name": "A", "phone": "9876543210"}},
    }
    with pytest.raises(ValidationError):
        Annotation.model_validate({"session_id": SESSION, "expect": real_looking})


def test_timing_from_the_two_channels(tmp_path: Path) -> None:
    timing = recording_timing(_recording(tmp_path))
    assert timing is not None
    assert timing["response_latencies_ms"] == [500]
    assert timing["wer_words"] == 0  # no script for a real caller


def test_no_channels_no_timing(tmp_path: Path) -> None:
    assert recording_timing(tmp_path) is None


async def test_a_recorded_call_is_scored_from_the_store(tmp_path: Path, menu: Menu) -> None:
    _recording(tmp_path)
    order = state.add_line(state.new_order(SESSION), menu, "masala_dosa", 2, None, [])
    order = state.mark_readback(state.set_customer(order, "Anil", "9000012345"))
    store = InMemoryOrderStore()
    await store.save(state.confirm(order))
    annotation = Annotation.model_validate({"session_id": SESSION, "expect": EXPECT})
    r = await score_recorded(annotation, store=store, recordings_dir=tmp_path)
    assert r.score.task_success, r.score.mismatches
    assert (r.mode, r.end_reason, r.turns, r.duration_s) == ("recorded", "recorded_call", 1, 60.0)
    assert (r.agent_model, r.caller_model) == ("gpt-6-luna", "human")
    assert r.audio is not None
    assert r.audio["response_latencies_ms"] == [500]
    assert r.audio["agent_cost_usd"] == 0.02


async def test_a_missing_recording_is_an_error(tmp_path: Path) -> None:
    annotation = Annotation.model_validate({"session_id": SESSION, "expect": EXPECT})
    r = await score_recorded(annotation, store=InMemoryOrderStore(), recordings_dir=tmp_path)
    assert r.end_reason == "error"
    assert r.error is not None
    assert "no recording" in r.error
    assert not r.score.task_success


def test_annotate_draft_starts_from_the_final_order(menu: Menu) -> None:
    order = state.add_line(state.new_order(SESSION), menu, "cold_coffee", 1, "large", ["oat_milk"])
    order = state.set_customer(order, "Priya", "9000023456")
    text = draft(SESSION, order)
    assert text.startswith("# What the caller WANTED")
    annotation = Annotation.model_validate(yaml.safe_load(text))
    assert annotation.expect.status == "confirmed"
    assert annotation.expect.order is not None
    item = annotation.expect.order.items[0]
    assert (item.item, item.size, item.modifiers) == ("cold_coffee", "large", ["oat_milk"])


def test_annotate_draft_without_an_order() -> None:
    annotation = Annotation.model_validate(yaml.safe_load(draft(SESSION, None)))
    assert annotation.expect.order is None
