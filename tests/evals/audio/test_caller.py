"""Pure helpers of the audio caller."""

import pytest
from evals.audio.caller import (
    STUCK_QUIET_S,
    VOICE_POOL,
    AgentState,
    speakable,
    tts_instructions,
)
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
