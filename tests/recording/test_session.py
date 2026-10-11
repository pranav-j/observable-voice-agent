"""Splitting the stereo recording, and extracting the transcript and tool calls."""

import json
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import av
import numpy as np
from livekit.agents.llm import ChatContext, ChatMessage, FunctionCall, FunctionCallOutput

from voice_order.recording.session import SAMPLE_RATE, split_channels, tool_calls, transcript


def write_stereo_ogg(path: Path, seconds: float = 1.0) -> None:
    """Left channel: a 440 Hz tone (the caller). Right channel: silence (the agent)."""
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n) / SAMPLE_RATE
    left = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    stereo = np.column_stack([left, np.zeros(n, dtype=np.int16)]).reshape(1, -1)
    with av.open(str(path), "w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=SAMPLE_RATE, layout="stereo")
        frame = av.AudioFrame.from_ndarray(stereo, format="s16", layout="stereo")
        frame.sample_rate = SAMPLE_RATE
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def rms(path: Path) -> tuple[float, int, int]:
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
        return (
            float(np.sqrt(np.mean(data**2))) if data.size else 0.0,
            w.getframerate(),
            w.getnchannels(),
        )


def test_split_channels_puts_the_caller_left_and_the_agent_right(tmp_path: Path) -> None:
    stereo = tmp_path / "audio.ogg"
    write_stereo_ogg(stereo)
    caller, agent = split_channels(stereo, tmp_path)
    caller_rms, rate, channels = rms(caller)
    agent_rms, _, _ = rms(agent)
    assert (rate, channels) == (SAMPLE_RATE, 1)
    assert caller_rms > 5000  # the tone
    assert agent_rms < caller_rms / 50  # silence, give or take codec noise


def fake_report(items: list[Any]) -> Any:
    return cast(Any, SimpleNamespace(chat_history=ChatContext(items=items)))


def test_transcript_keeps_spoken_messages_in_order() -> None:
    report = fake_report(
        [
            ChatMessage(role="system", content=["You are an order-taker."]),
            ChatMessage(role="assistant", content=["Hi, what would you like?"]),
            ChatMessage(role="user", content=["A dosa"]),
            ChatMessage(role="assistant", content=["One dosa, got it."], interrupted=True),
        ]
    )
    rows = transcript(report)
    assert [(r["role"], r["text"], r["interrupted"]) for r in rows] == [
        ("assistant", "Hi, what would you like?", False),
        ("user", "A dosa", False),
        ("assistant", "One dosa, got it.", True),
    ]


def test_tool_calls_are_paired_with_their_results() -> None:
    report = fake_report(
        [
            FunctionCall(
                call_id="c1", name="add_item", arguments='{"item_id": "masala_dosa", "quantity": 1}'
            ),
            FunctionCallOutput(
                call_id="c1", name="add_item", output='{"ok": true}', is_error=False
            ),
            FunctionCall(call_id="c2", name="end_call", arguments='{"reason": "done"}'),
        ]
    )
    calls = tool_calls(report)
    assert [(c["name"], c["arguments"], c["result"]) for c in calls] == [
        ("add_item", {"item_id": "masala_dosa", "quantity": 1}, {"ok": True}),
        ("end_call", {"reason": "done"}, None),
    ]
    assert json.dumps(calls)  # serializable as written to tool_calls.jsonl
