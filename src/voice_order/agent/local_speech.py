"""Local speech for the voice worker: Whisper hears the caller, Kokoro speaks.

Speech was nearly all of the per-call cost with hosted models (recognition about 60%,
the voices most of the rest), while the LLM was about 1%. These adapters run both on
the machine instead. They plug into LiveKit like its own plugins: recognition is
non-streaming, so LiveKit runs it on each utterance its voice detection finds, and
speech is synthesized a sentence at a time.

Inference is CPU work, so it runs in a thread to keep the call's event loop free. The
models load on first use, or ahead of time from the worker's prewarm.
"""

import asyncio
import threading
from pathlib import Path
from typing import Any, Never

import numpy as np
from livekit import rtc
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectOptions,
    LanguageCode,
    stt,
    tts,
    utils,
)
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import AudioBuffer

WHISPER_RATE = 16_000
KOKORO_RATE = 24_000


def to_whisper_input(frame: rtc.AudioFrame) -> np.ndarray[Any, Any]:
    """An audio frame as Whisper wants it: mono float32 at 16 kHz."""
    samples = np.frombuffer(bytes(frame.data), dtype=np.int16).astype(np.float32) / 32768
    if frame.num_channels > 1:
        samples = samples.reshape(-1, frame.num_channels).mean(axis=1)
    if frame.sample_rate == WHISPER_RATE or len(samples) == 0:
        return samples
    duration = len(samples) / frame.sample_rate
    target = np.linspace(0, duration, int(duration * WHISPER_RATE), endpoint=False)
    source = np.arange(len(samples)) / frame.sample_rate
    return np.interp(target, source, samples).astype(np.float32)


def to_pcm16(audio: np.ndarray[Any, Any]) -> bytes:
    return np.asarray(np.clip(audio, -1.0, 1.0) * 32767, dtype=np.int16).tobytes()


class WhisperSTT(stt.STT[Never]):  # no extra events beyond LiveKit's own
    def __init__(self, *, model: str = "base.en", language: str = "en") -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self._model_name = model
        self._language = language
        self._whisper: Any = None
        self._load_lock = threading.Lock()

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def provider(self) -> str:
        return "local"

    def load(self) -> None:
        with self._load_lock:
            if self._whisper is None:
                from faster_whisper import WhisperModel  # heavy import, only when used

                self._whisper = WhisperModel(self._model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray[Any, Any]) -> str:
        self.load()
        segments, _ = self._whisper.transcribe(audio, language=self._language, beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        audio = to_whisper_input(rtc.combine_audio_frames(buffer))
        text = await asyncio.to_thread(self.transcribe, audio)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=utils.shortuuid(),
            alternatives=[stt.SpeechData(language=LanguageCode(self._language), text=text)],
        )


class KokoroTTS(tts.TTS[Never]):  # no extra events beyond LiveKit's own
    def __init__(
        self,
        *,
        model_dir: Path,
        voice: str = "af_heart",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=KOKORO_RATE,
            num_channels=1,
        )
        self._model_dir = model_dir
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self._kokoro: Any = None
        self._load_lock = threading.Lock()

    @property
    def model(self) -> str:
        return "kokoro-v1.0"

    @property
    def provider(self) -> str:
        return "local"

    def load(self) -> None:
        with self._load_lock:
            if self._kokoro is None:
                from kokoro_onnx import Kokoro  # heavy import, only when used

                self._kokoro = Kokoro(
                    str(self._model_dir / "kokoro-v1.0.onnx"),
                    str(self._model_dir / "voices-v1.0.bin"),
                )

    def speak(self, text: str) -> bytes:
        self.load()
        audio, rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang=self.lang)
        if rate != KOKORO_RATE:
            raise RuntimeError(f"Kokoro returned {rate} Hz audio, expected {KOKORO_RATE}")
        return to_pcm16(audio)

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        return KokoroStream(tts=self, input_text=text, conn_options=conn_options)


class KokoroStream(tts.ChunkedStream):
    def __init__(self, *, tts: KokoroTTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._kokoro_tts = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=KOKORO_RATE,
            num_channels=1,
            mime_type="audio/pcm",
        )
        pcm = await asyncio.to_thread(self._kokoro_tts.speak, self.input_text)
        output_emitter.push(pcm)
        output_emitter.flush()
