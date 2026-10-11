"""Pure helpers of the audio caller."""

import numpy as np
import pytest
from evals.audio.caller import (
    STUCK_QUIET_S,
    VOICE_POOL,
    AgentState,
    AudioCaller,
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
