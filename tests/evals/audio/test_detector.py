"""The onset detector on synthetic audio, where the right answer is known exactly."""

import numpy as np
import pytest
from evals.audio.detector import SAMPLE_RATE, Segment, frame_levels, speech_segments


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.int16)


def tone(seconds: float, dbfs: float = -12.0) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    amplitude = 10 ** (dbfs / 20) * 32767 * np.sqrt(2)  # sine RMS = peak / sqrt(2)
    return np.asarray(amplitude * np.sin(2 * np.pi * 300 * t), dtype=np.int16)


def segments(*parts: np.ndarray) -> list[Segment]:
    return speech_segments(np.concatenate(parts))


def close(a: list[Segment], b: list[tuple[float, float]]) -> bool:
    return len(a) == len(b) and all(
        abs(s.start - x) <= 0.011 and abs(s.end - y) <= 0.011
        for s, (x, y) in zip(a, b, strict=True)
    )


def test_frame_levels_match_the_tone_level() -> None:
    levels = frame_levels(tone(0.1, dbfs=-12.0))
    assert np.allclose(levels, -12.0, atol=0.5)


def test_one_utterance() -> None:
    assert close(segments(silence(1.0), tone(0.5), silence(1.0)), [(1.0, 1.5)])


def test_short_gaps_join_one_utterance() -> None:
    found = segments(silence(1.0), tone(0.5), silence(0.2), tone(0.3), silence(1.0))
    assert close(found, [(1.0, 2.0)])


def test_long_gaps_split_utterances() -> None:
    found = segments(silence(0.5), tone(0.4), silence(0.6), tone(0.4), silence(0.5))
    assert close(found, [(0.5, 0.9), (1.5, 1.9)])


def test_clicks_shorter_than_min_speech_are_ignored() -> None:
    assert segments(silence(0.5), tone(0.02), silence(0.5)) == []


@pytest.mark.parametrize("dbfs", [-50.0, -60.0])
def test_quiet_sound_below_threshold_is_not_speech(dbfs: float) -> None:
    assert segments(silence(0.5), tone(0.5, dbfs=dbfs), silence(0.5)) == []


def test_speech_running_to_the_end_is_closed() -> None:
    assert close(segments(silence(0.3), tone(0.5)), [(0.3, 0.8)])


def test_empty_audio() -> None:
    assert speech_segments(np.zeros(0, dtype=np.int16)) == []
