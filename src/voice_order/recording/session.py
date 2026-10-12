"""Save everything about a finished call to recordings/<session_id>/.

- audio.ogg: LiveKit's stereo recording (left channel caller, right channel agent)
- caller.wav, agent.wav: the two channels split out, 16-bit 48 kHz
- transcript.json: who said what, in order
- tool_calls.jsonl: every tool call with its arguments and result
- report.json: LiveKit's full session report (events, chat history, usage)
- usage.json: provider usage and estimated cost (see config/rates.yaml)

turns.jsonl is written live during the call by the turn log.
"""

import json
import shutil
import wave
from pathlib import Path
from typing import Any

import av
import numpy as np
from livekit.agents.llm import ChatMessage, FunctionCall, FunctionCallOutput
from livekit.agents.voice.report import SessionReport

from voice_order.telemetry.usage import Rates, summarize_usage

SAMPLE_RATE = 48_000


def split_channels(stereo_path: Path, out_dir: Path) -> tuple[Path, Path]:
    """Decode a stereo recording and write each channel as its own mono WAV."""
    left: list[np.ndarray[Any, Any]] = []
    right: list[np.ndarray[Any, Any]] = []
    resampler = av.AudioResampler(format="s16", layout="stereo", rate=SAMPLE_RATE)
    with av.open(str(stereo_path)) as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                samples = out.to_ndarray().reshape(-1, 2)  # packed s16: L R L R ...
                left.append(samples[:, 0])
                right.append(samples[:, 1])
    paths = (out_dir / "caller.wav", out_dir / "agent.wav")
    for path, chunks in zip(paths, (left, right), strict=True):
        data = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(data.astype(np.int16).tobytes())
    return paths


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def transcript(report: SessionReport) -> list[dict[str, Any]]:
    return [
        {
            "role": item.role,
            "text": item.text_content or "",
            "interrupted": item.interrupted,
            "created_at": item.created_at,
        }
        for item in report.chat_history.items
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant")
    ]


def tool_calls(report: SessionReport) -> list[dict[str, Any]]:
    outputs = {
        item.call_id: item
        for item in report.chat_history.items
        if isinstance(item, FunctionCallOutput)
    }
    calls = []
    for item in report.chat_history.items:
        if not isinstance(item, FunctionCall):
            continue
        out = outputs.get(item.call_id)
        try:
            result: Any = json.loads(out.output) if out else None
        except json.JSONDecodeError:
            result = out.output if out else None
        calls.append(
            {
                "name": item.name,
                "arguments": json.loads(item.arguments or "{}"),
                "result": result,
                "created_at": item.created_at,
            }
        )
    return calls


def save_session(report: SessionReport, out_dir: Path, rates: Rates) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = Path(report.audio_recording_path) if report.audio_recording_path else None
    recorded_seconds: float | None = None
    if audio is not None and audio.exists():
        # The original lives in a temporary directory LiveKit deletes when the job ends.
        kept = out_dir / "audio.ogg"
        shutil.copyfile(audio, kept)
        caller_wav, _ = split_channels(kept, out_dir)
        recorded_seconds = wav_seconds(caller_wav)
    (out_dir / "transcript.json").write_text(json.dumps(transcript(report), indent=2))
    with (out_dir / "tool_calls.jsonl").open("w", encoding="utf-8") as f:
        for call in tool_calls(report):
            f.write(json.dumps(call, ensure_ascii=False) + "\n")
    (out_dir / "report.json").write_text(json.dumps(report.to_dict(), indent=2, default=str))
    # Speech-to-text with no reported duration is estimated from the call's length. Use the
    # recorded audio when there is some: the session clock kept running while the machine
    # slept, and once billed four short calls as over an hour each.
    call_seconds = recorded_seconds if recorded_seconds else report.duration
    usage = summarize_usage(list(report.model_usage or []), rates, call_seconds=call_seconds)
    usage["duration_seconds"] = report.duration
    (out_dir / "usage.json").write_text(json.dumps(usage, indent=2))
    return out_dir
