"""The simulated caller as a real participant in a LiveKit room.

It speaks with text-to-speech over a continuous noise bed, logging exactly when each
utterance and scripted pause goes out. It listens to the agent: the received audio is
kept for offline scoring, its loudness is tracked live for turn-taking, and the agent's
words come from LiveKit's transcription stream (or the caller's own STT). It also watches
the worker's order updates to notice when the read-back starts.
"""

import asyncio
import contextlib
import io
import json
import re
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from livekit import rtc
from openai import AsyncOpenAI

from evals.audio.detector import SAMPLE_RATE as LISTEN_RATE
from evals.audio.detector import LiveSpeech, speech_segments
from evals.audio.metrics import CallerUtterance, Timeline
from evals.audio.noise import SAMPLE_RATE as SPEAK_RATE
from evals.audio.noise import noise_bed, speech_at_level, to_pcm16

FRAME = SPEAK_RATE // 100  # 10 ms
Hearing = Literal["transcript", "stt"]
# If the agent's transcript stream never closes, this much silence still ends its turn.
STUCK_QUIET_S = 5.0

# Scenario voices -> OpenAI TTS voices. Changing this changes what callers sound like,
# so reports record the pool.
VOICE_POOL = {
    "voice_pool.female_1": "nova",
    "voice_pool.female_2": "shimmer",
    "voice_pool.female_3": "coral",
    "voice_pool.male_1": "onyx",
    "voice_pool.male_2": "echo",
    "voice_pool.male_3": "ash",
}
DEFAULT_VOICE = "alloy"
STYLE_INSTRUCTIONS = {
    "brisk": "brisk and to the point",
    "chatty": "friendly and relaxed",
    "hesitant": "hesitant, unsure, with natural small pauses",
    "confused": "a little unsure and confused",
    "adversarial": "pushy and impatient",
}


def speakable(text: str) -> str:
    """Write long digit runs the way people read out a phone number.

    Text-to-speech reads "9000000002" as a number ("nine billion..."), which no caller
    would say. Runs of 5+ digits become single digits, grouped in fives: "9 0 0 0 0, 0 0 0 0 2".
    """

    def spell(match: re.Match[str]) -> str:
        digits = match.group()
        groups = [" ".join(digits[i : i + 5]) for i in range(0, len(digits), 5)]
        return ", ".join(groups)

    text = re.sub(r"\+\s?91[\s-]*", "plus nine one, ", text)
    return re.sub(r"\d{5,}", spell, re.sub(r"(?<=\d)[ -](?=\d)", "", text))


def split_for_pause(text: str) -> tuple[str, str]:
    """Where a scripted pause goes: before the last five digits of a phone number, the
    way people pause between the two halves, or else halfway through the words."""
    number = re.search(r"\d(?:[ -]?\d){9,}", text)
    if number:
        positions = [i for i in range(number.start(), number.end()) if text[i].isdigit()]
        cut = positions[-5]
        return text[:cut].rstrip(" -"), text[cut:]
    words = text.split()
    half = len(words) // 2
    return " ".join(words[:half]), " ".join(words[half:])


def tts_instructions(style: str) -> str:
    return (
        "You are a customer phoning a restaurant to order food. Speak in Indian English, "
        f"{STYLE_INSTRUCTIONS.get(style, 'natural')}."
    )


@dataclass
class _Speech:
    pcm: np.ndarray[Any, Any]  # float at speech level
    pauses: list[tuple[int, int]]  # (sample offset where a pause starts, pause length in samples)
    done: asyncio.Future[CallerUtterance]
    text: str
    interrupt: bool


@dataclass
class AgentState:
    last_loud: float = 0.0
    onset: float = 0.0  # last time agent speech started after a quiet spell
    transcripts: list[tuple[float, str]] = field(default_factory=list)
    readback_started: float | None = None
    order_status: str = "draft"
    left: bool = False
    open_streams: int = 0  # agent transcript streams still being written

    def done_speaking(self, since: float, now: float, quiet: float) -> bool:
        """Has the agent spoken since `since` and finished?

        Silence alone isn't enough: in a long reply the gap between two sentences, while
        the next one is synthesized, can outlast `quiet`. LiveKit keeps the transcript
        stream for an utterance open until it has been spoken, so wait for that too.
        """
        if self.left:
            return True
        if self.last_loud <= since:
            return False
        silent = now - self.last_loud
        return (silent >= quiet and self.open_streams == 0) or silent >= STUCK_QUIET_S


class AudioCaller:
    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        voice: str,
        style: str,
        noise: tuple[str, float] | None,
        hearing: Hearing = "transcript",
    ) -> None:
        self.client = client
        self.voice = VOICE_POOL.get(voice, DEFAULT_VOICE)
        self.instructions = tts_instructions(style)
        self.noise = noise
        self.hearing = hearing
        self.room = rtc.Room()
        self.identity = ""
        self.t0 = time.monotonic()
        self.agent = AgentState()
        self.utterances: list[CallerUtterance] = []
        self.heard_caller: list[tuple[float, str]] = []
        self._agent_frames: list[np.ndarray[Any, Any]] = []
        self._agent_audio_start: float | None = None
        self._queue: asyncio.Queue[_Speech] = asyncio.Queue()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._changed = asyncio.Event()  # set whenever anything about the agent changes

    def now(self) -> float:
        return time.monotonic() - self.t0

    # --- joining and listening ---------------------------------------------------

    async def join(self, url: str, token: str, identity: str) -> None:
        self.identity = identity
        self.room.on("track_subscribed", self._on_track)
        self.room.on("data_received", self._on_data)
        self.room.on("participant_disconnected", self._on_left)
        self.room.register_text_stream_handler("lk.transcription", self._on_transcript)
        await self.room.connect(url, token)
        source = rtc.AudioSource(SPEAK_RATE, 1, queue_size_ms=50)  # small buffer: honest timestamps
        track = rtc.LocalAudioTrack.create_audio_track("caller-mic", source)
        await self.room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        self._spawn(self._speak_loop(source))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _on_track(self, track: rtc.Track, pub: Any, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            self._spawn(self._listen(track))

    async def _listen(self, track: rtc.Track) -> None:
        quiet_since = self.now()
        speech = LiveSpeech()  # same onset rule as the offline detector
        stream = rtc.AudioStream(track, sample_rate=LISTEN_RATE, num_channels=1)
        async for event in stream:
            t = self.now()
            samples = np.frombuffer(bytes(event.frame.data), dtype=np.int16)
            if self._agent_audio_start is None:
                self._agent_audio_start = t - len(samples) / LISTEN_RATE
            self._agent_frames.append(samples.copy())
            if speech.feed(samples):
                if t - self.agent.last_loud > 0.3:
                    self.agent.onset = t
                    self._changed.set()
                self.agent.last_loud = t
            elif t - self.agent.last_loud > 0.3 and quiet_since < self.agent.last_loud:
                quiet_since = t
                self._changed.set()

    def _on_transcript(self, reader: rtc.TextStreamReader, participant_identity: str) -> None:
        agent = participant_identity != self.identity
        if agent:
            self.agent.open_streams += 1

        async def read() -> None:
            try:
                text = (await reader.read_all()).strip()
            finally:
                if agent:
                    self.agent.open_streams -= 1
                    self._changed.set()
            final = (reader.info.attributes or {}).get("lk.transcription_final") == "true"
            if not (final and text):
                return
            if participant_identity == self.identity:
                self.heard_caller.append((self.now(), text))  # the agent's STT of us, for WER
            else:
                self.agent.transcripts.append((self.now(), text))
                self._changed.set()

        self._spawn(read())

    def _on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != "order":
            return
        view = json.loads(packet.data)
        self.agent.order_status = view.get("status", "draft")
        if view.get("readback_current") and self.agent.readback_started is None:
            self.agent.readback_started = self.now()
        elif not view.get("readback_current"):
            self.agent.readback_started = None
        self._changed.set()

    def _on_left(self, participant: rtc.RemoteParticipant) -> None:
        self.agent.left = True
        self._changed.set()

    # --- speaking ------------------------------------------------------------------

    async def _speak_loop(self, source: rtc.AudioSource) -> None:
        """Send noise all the time, with queued speech mixed on top."""
        offset = 0
        current: _Speech | None = None
        pos = 0
        started = 0.0
        pause_windows: list[tuple[float, float]] = []
        pauses: list[tuple[int, int]] = []
        while True:
            if current is None and not self._queue.empty():
                current, pos, started, pause_windows = self._queue.get_nowait(), 0, self.now(), []
                pauses = sorted(current.pauses)
            frame = np.zeros(FRAME)
            if current is not None:
                if pauses and pos >= pauses[0][0]:  # inside a scripted pause: silence (plus noise)
                    if not pause_windows or pause_windows[-1][1] >= 0:
                        pause_windows.append((self.now(), -1.0))
                    pauses[0] = (pauses[0][0], pauses[0][1] - FRAME)
                    if pauses[0][1] <= 0:
                        pause_windows[-1] = (pause_windows[-1][0], self.now())
                        pauses.pop(0)
                else:
                    chunk = current.pcm[pos : pos + FRAME]
                    frame[: len(chunk)] = chunk
                    pos += FRAME
                if pos >= len(current.pcm) and not pauses:
                    end = self.now()
                    utterance = CallerUtterance(
                        current.text,
                        started,
                        end,
                        tuple(w for w in pause_windows if w[1] >= 0),
                        current.interrupt,
                    )
                    self.utterances.append(utterance)
                    current.done.set_result(utterance)
                    current = None
            if self.noise is not None:
                frame = frame + noise_bed(self.noise[0], self.noise[1], FRAME, offset)
            offset += FRAME
            await source.capture_frame(
                rtc.AudioFrame(to_pcm16(frame).tobytes(), SPEAK_RATE, 1, FRAME)
            )

    async def synthesize(self, text: str) -> np.ndarray[Any, Any]:
        response = await self.client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=self.voice,
            input=speakable(text),
            instructions=self.instructions,
            response_format="pcm",
        )
        return speech_at_level(np.frombuffer(response.content, dtype=np.int16))

    async def say(
        self, text: str, *, pause_ms: int = 0, interrupt: bool = False
    ) -> CallerUtterance:
        """Speak `text`. With pause_ms, a silence is inserted where `split_for_pause` says."""
        first, second = split_for_pause(text)
        if pause_ms and first and second:
            a, b = await asyncio.gather(self.synthesize(first), self.synthesize(second))
            pcm = np.concatenate([a, b])
            pauses = [(len(a), int(SPEAK_RATE * pause_ms / 1000))]
        else:
            pcm, pauses = await self.synthesize(text), []
        done: asyncio.Future[CallerUtterance] = asyncio.get_running_loop().create_future()
        await self._queue.put(_Speech(pcm, pauses, done, text, interrupt))
        return await done

    # --- waiting for the agent -------------------------------------------------------

    async def wait_until(self, condition: Any, max_wait: float) -> bool:
        deadline = self.now() + max_wait
        while not condition():
            remaining = deadline - self.now()
            if remaining <= 0:
                return False
            self._changed.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), timeout=min(remaining, 0.2))
        return True

    async def agent_reply(self, since: float, max_wait: float = 30.0, quiet: float = 1.2) -> str:
        """Wait for the agent to speak after `since` and finish; return what it said."""
        await self.wait_until(lambda: self.agent.done_speaking(since, self.now(), quiet), max_wait)
        if self.hearing == "stt":
            return await self._transcribe_agent(since)
        await asyncio.sleep(0.3)  # the final transcript can land just after the audio ends
        return " ".join(text for t, text in self.agent.transcripts if t > since)

    async def agent_speaking_after(self, since: float, max_wait: float = 30.0) -> float | None:
        """Wait for agent speech to start after `since`; return when it did."""
        ok = await self.wait_until(lambda: self.agent.onset > since or self.agent.left, max_wait)
        return self.agent.onset if ok and self.agent.onset > since else None

    async def _transcribe_agent(self, since: float) -> str:
        audio, start = self.agent_audio()
        segments = [s for s in speech_segments(audio) if s.start + start > since]
        if not segments:
            return ""
        a = int((segments[0].start) * LISTEN_RATE)
        b = int((segments[-1].end) * LISTEN_RATE)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(LISTEN_RATE)
            w.writeframes(audio[a:b].tobytes())
        result = await self.client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe", file=("agent.wav", buffer.getvalue())
        )
        return result.text

    # --- results ---------------------------------------------------------------------

    def agent_audio(self) -> tuple[np.ndarray[Any, Any], float]:
        audio = (
            np.concatenate(self._agent_frames)
            if self._agent_frames
            else np.zeros(0, dtype=np.int16)
        )
        return audio, self._agent_audio_start or 0.0

    def timeline(self) -> Timeline:
        audio, start = self.agent_audio()
        return Timeline(
            caller=list(self.utterances),
            agent_audio=audio,
            agent_audio_start=start,
            heard_caller=list(self.heard_caller),
        )

    async def leave(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.room.disconnect()
