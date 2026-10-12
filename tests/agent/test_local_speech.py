"""Local speech adapters, with stand-ins for the models so no model files are needed."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from livekit import rtc
from livekit.agents import stt

from voice_order.agent.local_speech import KOKORO_RATE, KokoroTTS, WhisperSTT, to_whisper_input


def _frame(seconds: float, rate: int, channels: int) -> rtc.AudioFrame:
    n = int(seconds * rate)
    samples = (np.full(n * channels, 0.25) * 32767).astype(np.int16)
    return rtc.AudioFrame(samples.tobytes(), rate, channels, n)


def test_whisper_input_is_mono_16k_float() -> None:
    audio = to_whisper_input(_frame(0.5, 48_000, 2))
    assert audio.dtype == np.float32
    assert len(audio) == 8000
    assert np.allclose(audio, 0.25, atol=1e-3)


def test_16k_mono_passes_through() -> None:
    assert len(to_whisper_input(_frame(1.0, 16_000, 1))) == 16_000


class _FakeWhisper:
    def __init__(self) -> None:
        self.seen: list[int] = []

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[Any], None]:
        self.seen.append(len(audio))
        return [SimpleNamespace(text=" Two masala"), SimpleNamespace(text=" dosas, please. ")], None


async def test_recognize_returns_one_final_transcript() -> None:
    whisper = WhisperSTT(model="small.en")
    fake = _FakeWhisper()
    whisper._whisper = fake
    event = await whisper.recognize([_frame(1.0, 48_000, 1)])
    assert event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert event.alternatives[0].text == "Two masala dosas, please."
    assert fake.seen == [16_000]
    assert (whisper.model, whisper.provider) == ("small.en", "local")


class _FakeKokoro:
    def create(self, text: str, **kwargs: Any) -> tuple[np.ndarray[Any, Any], int]:
        return np.full(KOKORO_RATE // 2, 0.1, dtype=np.float32), KOKORO_RATE  # half a second


async def test_kokoro_synthesizes_pcm_through_livekit() -> None:
    voice = KokoroTTS(model_dir=Path("unused"), voice="af_heart")
    voice._kokoro = _FakeKokoro()
    samples = 0
    async with voice.synthesize("What name should I put on the order?") as stream:
        async for event in stream:
            samples += event.frame.samples_per_channel
    # All of it arrives; LiveKit may pad the end of a segment by a frame.
    assert KOKORO_RATE // 2 <= samples < KOKORO_RATE // 2 + KOKORO_RATE // 20
    assert (voice.model, voice.provider) == ("kokoro-v1.0", "local")
