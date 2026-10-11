"""Pure helpers of the audio caller."""

import pytest
from evals.audio.caller import VOICE_POOL, speakable, tts_instructions
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
