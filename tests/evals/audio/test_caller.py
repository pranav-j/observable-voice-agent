"""Pure helpers of the audio caller."""

import asyncio
from typing import Any

import numpy as np
import pytest
from evals.audio.caller import (
    MIN_LINE_SECONDS,
    STUCK_QUIET_S,
    VOICE_POOL,
    AgentState,
    AudioCaller,
    pause_point,
    speakable,
    split_for_pause,
    tts_instructions,
)
from evals.audio_run import gives_phone_number
from evals.scenario import load_scenarios


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("9000000002.", "9 0 0 0 0, 0 0 0 0 2."),
        ("It's 90000 00025", "It's 9 0 0 0 0, 0 0 0 2 5"),
        ("+91 90000 00025", "plus nine one, 9 0 0 0 0, 0 0 0 2 5"),
        ("Two masala dosas, please", "Two masala dosas, please"),
        ("Table for 4 at 7", "Table for 4 at 7"),
    ],
)
def test_speakable_reads_numbers_out_digit_by_digit(text: str, spoken: str) -> None:
    assert speakable(text) == spoken


def test_every_scenario_voice_is_in_the_pool() -> None:
    voices = {s.persona.voice for s in load_scenarios() if s.persona.voice}
    assert voices <= set(VOICE_POOL), voices - set(VOICE_POOL)


def test_tts_instructions_mention_the_style() -> None:
    assert "hesitant" in tts_instructions("hesitant")


def test_agent_is_not_done_before_it_speaks() -> None:
    agent = AgentState(last_loud=4.0)
    assert not agent.done_speaking(since=5.0, now=20.0, quiet=1.2)


def test_agent_is_done_after_quiet_with_no_open_transcript() -> None:
    agent = AgentState(last_loud=10.0)
    assert not agent.done_speaking(since=5.0, now=11.0, quiet=1.2)
    assert agent.done_speaking(since=5.0, now=11.3, quiet=1.2)


def test_a_pause_between_sentences_is_not_the_end() -> None:
    # The read-back is still being spoken: its transcript stream hasn't closed.
    agent = AgentState(last_loud=10.0, open_streams=1)
    assert not agent.done_speaking(since=5.0, now=12.5, quiet=1.2)


def test_long_silence_ends_the_turn_even_if_a_stream_never_closes() -> None:
    agent = AgentState(last_loud=10.0, open_streams=1)
    assert agent.done_speaking(since=5.0, now=10.0 + STUCK_QUIET_S, quiet=1.2)


def test_agent_leaving_ends_the_wait() -> None:
    assert AgentState(left=True).done_speaking(since=5.0, now=6.0, quiet=1.2)


@pytest.mark.parametrize(
    ("text", "first", "second"),
    [
        ("It's 9000026457.", "It's 90000", "26457."),
        ("+91 90000 26457", "+91 90000", "26457"),
        ("9000-026-457 please", "9000-0", "26-457 please"),
        ("one chicken tikka roll please", "one chicken", "tikka roll please"),
    ],
)
def test_pause_goes_between_the_halves_of_a_phone_number(
    text: str, first: str, second: str
) -> None:
    assert split_for_pause(text) == (first, second)


def test_phone_number_utterances_are_recognized() -> None:
    assert gives_phone_number("It's 90000 26457.")
    assert gives_phone_number("nine zero zero zero zero, two six four five seven")
    assert not gives_phone_number("Two masala dosas and one coffee, please.")


class _FakeSpeech:
    """Stands in for the OpenAI client: returns the queued audio lengths in order."""

    def __init__(self, *seconds: float) -> None:
        self.seconds = list(seconds)
        self.calls = 0
        self.audio = self
        self.speech = self

    async def create(self, **kwargs: object) -> object:
        self.calls += 1
        n = int(self.seconds.pop(0) * 24_000)
        tone = (3000 * np.sin(np.arange(n) / 5)).astype(np.int16)
        return type("Response", (), {"content": tone.tobytes()})()


def _caller(fake: _FakeSpeech) -> AudioCaller:
    return AudioCaller(client=fake, voice="", style="brisk", noise=None)  # type: ignore[arg-type]


async def test_clipped_speech_is_retried() -> None:
    fake = _FakeSpeech(0.1, 1.5)
    pcm = await _caller(fake).synthesize("Yes. Goodbye.")
    assert fake.calls == 2
    assert len(pcm) == int(1.5 * 24_000)


async def test_speech_that_stays_clipped_is_a_harness_error() -> None:
    fake = _FakeSpeech(0.1, 0.1, 0.1)
    with pytest.raises(RuntimeError, match="clipped"):
        await _caller(fake).synthesize("Yes. Goodbye.")


async def test_a_one_word_line_still_has_a_floor() -> None:
    fake = _FakeSpeech(0.3, 1.0)  # "Pooja." once came back as 0.3 s and was never heard
    await _caller(fake).synthesize("Pooja.")
    assert fake.calls == 2


def test_heard_since_includes_lines_still_being_written() -> None:
    agent = AgentState(transcripts=[(1.0, "Old line."), (5.0, "Sure.")])
    agent.live[1] = (6.0, "Let me read that back. One dosa.")
    agent.live[2] = (7.0, "")  # opened, nothing written yet
    assert agent.heard_since(4.0) == "Sure. Let me read that back. One dosa."


def test_a_late_closing_line_belongs_to_when_it_started() -> None:
    # The read-back's stream closed only after the caller's next words (at 20.0), but it
    # started at 10.0, so the next reply (since 20.0) doesn't repeat it.
    agent = AgentState(transcripts=[(10.0, "Let me read that back."), (22.0, "Done.")])
    assert agent.heard_since(20.0) == "Done."


class _FakeKokoro:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, text: str, **kwargs: Any) -> tuple[np.ndarray[Any, Any], int]:
        self.calls.append({"text": text, **kwargs})
        return np.full(3 * 24_000, 0.2, dtype=np.float32), 24_000  # long enough for the line


async def test_caller_can_speak_with_kokoro() -> None:
    kokoro = _FakeKokoro()
    caller = AudioCaller(
        client=None,  # type: ignore[arg-type]
        voice="voice_pool.female_1",
        style="hesitant",
        noise=None,
        voice_provider="kokoro",
        kokoro=kokoro,
    )
    pcm = await caller.synthesize("It's 9876523456.")
    assert len(pcm) == 3 * 24_000 + 24_000 // 2  # the speech plus half a second of silence
    (call,) = kokoro.calls
    assert (call["voice"], call["speed"]) == ("hf_alpha", 0.9)
    assert call["text"] == speakable("It's 9876523456.")  # digits still read out one by one


async def test_a_one_word_kokoro_line_passes_the_floor() -> None:
    class Short(_FakeKokoro):
        def create(self, text: str, **kwargs: Any) -> tuple[np.ndarray[Any, Any], int]:
            return np.full(int(0.45 * 24_000), 0.2, dtype=np.float32), 24_000  # "Neha."

    caller = AudioCaller(
        client=None,  # type: ignore[arg-type]
        voice="voice_pool.female_2",
        style="brisk",
        noise=None,
        voice_provider="kokoro",
        kokoro=Short(),
    )
    pcm = await caller.synthesize("Neha.")
    assert len(pcm) / 24_000 >= MIN_LINE_SECONDS


def _words(*seconds: float, gap: float = 0.08) -> np.ndarray[Any, Any]:
    """Tone bursts for words, with short near-silent gaps between them."""
    rate, parts = 24_000, [np.zeros(4_800, dtype=np.int16)]
    for s in seconds:
        n = int(s * rate)
        parts.append((6000 * np.sin(np.arange(n) / 5)).astype(np.int16))
        parts.append((30 * np.sin(np.arange(int(gap * rate)) / 5)).astype(np.int16))
    return np.concatenate([*parts, np.zeros(7_200, dtype=np.int16)])


def test_pause_is_cut_into_the_gap_nearest_the_split() -> None:
    pcm = _words(0.4, 0.4, 0.4, 0.4)  # four equal words
    text = "aaaa bbbb cccc dddd"
    first, _ = split_for_pause(text)
    cut = pause_point(pcm, text, first)
    gap_start = 4_800 + int(2 * 0.4 * 24_000) + int(0.08 * 24_000)  # after the second word
    assert gap_start <= cut < gap_start + int(0.08 * 24_000)


def test_pause_point_falls_back_to_the_middle_of_silence() -> None:
    assert pause_point(np.zeros(24_000, dtype=np.int16), "a b", "a") == 12_000


async def test_a_paused_line_is_spoken_in_one_piece() -> None:
    kokoro = _FakeKokoro()
    caller = AudioCaller(
        client=None,  # type: ignore[arg-type]
        voice="voice_pool.female_1",
        style="hesitant",
        noise=None,
        voice_provider="kokoro",
        kokoro=kokoro,
    )
    line = "Umm, could I get one Mysore masala dosa?"
    task = asyncio.create_task(caller.say(line, pause_ms=1500))
    speech = await caller._queue.get()
    task.cancel()
    assert [c["text"] for c in kokoro.calls] == [speakable(line)]
    ((at, length),) = speech.pauses
    assert 0 < at < len(speech.pcm)
    assert length == int(1.5 * 24_000)
