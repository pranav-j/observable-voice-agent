"""Audio metrics on hand-built timelines, where the right answers are known."""

import numpy as np
import pytest
from evals.audio.detector import SAMPLE_RATE
from evals.audio.metrics import (
    CallerUtterance,
    Timeline,
    audio_metrics,
    barge_in_stop_times,
    false_cutoffs,
    normalize_words,
    response_latencies,
    utterance_wer,
    word_errors,
)


def agent_audio(*speech: tuple[float, float], length: float = 30.0) -> np.ndarray:
    """Silence with loud tone where the agent 'speaks' (in seconds from the audio start)."""
    audio = np.zeros(int(SAMPLE_RATE * length), dtype=np.int16)
    for start, end in speech:
        n = int(SAMPLE_RATE * (end - start))
        t = np.arange(n) / SAMPLE_RATE
        audio[int(SAMPLE_RATE * start) : int(SAMPLE_RATE * start) + n] = (
            8000 * np.sin(2 * np.pi * 220 * t)
        ).astype(np.int16)
    return audio


def test_response_latency_from_utterance_end_to_agent_onset() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("one dosa", 2.0, 3.0), CallerUtterance("that's all", 8.0, 9.0)],
        agent_audio=agent_audio((4.2, 6.0), (10.5, 12.0)),
    )
    assert response_latencies(timeline) == pytest.approx([1.2, 1.5], abs=0.011)


def test_agent_audio_clock_offset_is_applied() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("hi", 12.0, 13.0)],
        agent_audio=agent_audio((4.0, 5.0)),
        agent_audio_start=10.0,  # agent audio began arriving at t=10 on the caller's clock
    )
    assert response_latencies(timeline) == pytest.approx([1.0], abs=0.011)


def test_no_value_when_the_agent_only_answers_after_the_caller_speaks_again() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("hello?", 1.0, 2.0), CallerUtterance("hello??", 4.0, 5.0)],
        agent_audio=agent_audio((6.0, 7.0)),
    )
    assert response_latencies(timeline) == pytest.approx([1.0], abs=0.011)


def test_barge_in_stop_time() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("sorry, make it medium", 5.0, 6.5, interrupt=True)],
        agent_audio=agent_audio((3.0, 5.4)),  # the agent stops 0.4 s after being interrupted
    )
    assert barge_in_stop_times(timeline) == pytest.approx([0.4], abs=0.011)


def test_interruption_when_the_agent_was_silent_is_not_counted() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("wait", 5.0, 5.5, interrupt=True)],
        agent_audio=agent_audio((1.0, 2.0)),
    )
    assert barge_in_stop_times(timeline) == []


def test_false_cutoff_when_the_agent_talks_before_the_caller_finishes() -> None:
    patient = Timeline(
        caller=[CallerUtterance("one masala dosa and a chai", 1.0, 5.0, pauses=((2.0, 3.2),))],
        agent_audio=agent_audio((6.0, 7.0)),
    )
    eager = Timeline(
        caller=[CallerUtterance("one masala dosa and a chai", 1.0, 5.0, pauses=((2.0, 3.2),))],
        agent_audio=agent_audio((4.0, 5.5)),  # replied to the pause while the caller went on
    )
    assert false_cutoffs(patient) == (0, 1)
    assert false_cutoffs(eager) == (1, 1)


def test_wer_normalizes_digits_and_punctuation() -> None:
    assert normalize_words("Nine zero zero, 90!") == ["nine", "zero", "zero", "nine", "zero"]
    assert word_errors(["a", "b", "c"], ["a", "x", "c", "d"]) == 2


def test_utterance_wer_uses_transcripts_that_arrive_shortly_after() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("one masala dosa please", 1.0, 3.0)],
        heard_caller=[(3.5, "One masala dose please."), (20.0, "unrelated")],
    )
    assert utterance_wer(timeline) == [(1, 4)]


def test_summary_counts_dead_air() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("a", 1.0, 2.0), CallerUtterance("b", 10.0, 11.0)],
        agent_audio=agent_audio((4.5, 6.0), (12.0, 13.0)),
    )
    summary = audio_metrics(timeline)
    assert summary["response_latencies_ms"] == pytest.approx([2500, 1000], abs=15)
    assert summary["dead_air_turns"] == 1
