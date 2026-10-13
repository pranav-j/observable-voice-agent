"""Audio metrics on hand-built timelines, where the right answers are known."""

from typing import Any

import numpy as np
import pytest
from evals.audio.detector import SAMPLE_RATE, Segment
from evals.audio.metrics import (
    CallerUtterance,
    Timeline,
    agent_timings,
    audio_metrics,
    barge_in_stop_times,
    doubled_replies,
    false_cutoffs,
    normalize_words,
    recording_metrics,
    response_latencies,
    speech_runs,
    turn_ends_in_pauses,
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


# --- recording_metrics: real calls -------------------------------------------------------


def test_recording_latency_counts_only_caller_to_agent_gaps() -> None:
    caller = [Segment(1.0, 2.0), Segment(2.4, 3.0), Segment(9.0, 9.5)]
    agent = [Segment(4.5, 6.0), Segment(6.5, 7.5), Segment(10.0, 11.0)]
    m = recording_metrics(caller, agent)
    # 3.0 -> 4.5 and 9.5 -> 10.0; 6.5 follows the agent's own sentence
    assert m["response_latencies_ms"] == [1500, 500]
    assert m["dead_air_turns"] == 0


def test_recording_agent_starting_over_the_caller_is_not_a_latency() -> None:
    m = recording_metrics([Segment(1.0, 4.0)], [Segment(3.0, 5.0)])
    assert m["response_latencies_ms"] == []


def test_recording_barge_in_stop() -> None:
    caller = [Segment(0.0, 1.0), Segment(3.0, 3.6)]
    agent = [Segment(1.5, 3.8)]
    m = recording_metrics(caller, agent)
    assert m["barge_in_stop_ms"] == [800]


def test_recording_dead_air() -> None:
    m = recording_metrics([Segment(0.0, 1.0)], [Segment(3.5, 4.0)])
    assert (m["response_latencies_ms"], m["dead_air_turns"]) == ([2500], 1)


def test_doubled_replies() -> None:
    assert (
        doubled_replies(
            [
                "May I have your name for the order?May I have your name for the order?",
                "Thanks. Thanks for calling.",
                "Got it. Got it.",
                "One coffee. What name?",
            ]
        )
        == 2
    )


def test_pauses_between_sentences_join_into_one_reply() -> None:
    segments = [Segment(1.0, 2.0), Segment(2.4, 3.0), Segment(6.0, 7.0)]
    assert speech_runs(segments) == [Segment(1.0, 3.0), Segment(6.0, 7.0)]


def test_barge_in_stop_runs_to_the_end_of_the_reply_not_the_sentence() -> None:
    # The agent ignores the caller (who starts at 2.0): it pauses for a sentence break at
    # 2.5 and carries on until 4.0. Before, this measured only the 0.5 s to the break.
    m = recording_metrics(
        [Segment(0.0, 1.0), Segment(2.0, 2.6)], [Segment(1.5, 2.5), Segment(2.8, 4.0)]
    )
    assert m["barge_in_stop_ms"] == [2000]


def test_agent_timings_keep_only_logged_numbers() -> None:
    records: list[dict[str, Any]] = [
        {"role": "user", "end_of_turn_delay": 0.6},
        {"role": "assistant", "llm_node_ttft": 1.1, "tts_node_ttfb": 1.0, "e2e_latency": 4.2},
        {"role": "assistant", "tts_node_ttfb": None},
    ]
    assert agent_timings(records) == {
        "end_of_turn_delay": [0.6],
        "llm_node_ttft": [1.1],
        "tts_node_ttfb": [1.0],
        "e2e_latency": [4.2],
    }


def test_turn_ended_in_a_pause_by_the_agents_clock() -> None:
    # The caller clock starts 1000 s after the agent's: the greeting is at agent time
    # 1001.0 and the caller hears it at 1.0.
    timeline = Timeline(
        caller=[CallerUtterance("one masala dosa and a chai", 5.0, 9.0, pauses=((6.0, 7.5),))],
        agent_audio=agent_audio((1.0, 3.0), (12.0, 13.0)),
    )
    greeting = {"role": "assistant", "started_speaking_at": 1001.0}

    def caller_turn(stopped: float, delay: float) -> dict[str, Any]:
        return {"role": "user", "stopped_speaking_at": stopped, "end_of_turn_delay": delay}

    early = [greeting, caller_turn(1006.0, 0.6), caller_turn(1009.0, 0.6)]  # committed at 6.6
    patient = [greeting, caller_turn(1009.0, 0.6)]  # waited out the pause
    # Committed 0.1 s after the pause ended, before the agent noticed the caller had resumed:
    # the sentence is still split in two.
    just_after = [greeting, caller_turn(1006.2, 1.4), caller_turn(1009.0, 1.4)]
    assert turn_ends_in_pauses(timeline, early) == 1
    assert turn_ends_in_pauses(timeline, just_after) == 1
    assert turn_ends_in_pauses(timeline, patient) == 0
    # Its audio came after the caller had finished, so the caller-side metric can't see it.
    assert false_cutoffs(timeline) == (0, 1)


def test_turn_ends_in_pauses_needs_both_clocks() -> None:
    timeline = Timeline(
        caller=[CallerUtterance("hello", 5.0, 9.0, pauses=((6.0, 7.5),))],
        agent_audio=agent_audio((1.0, 3.0)),
    )
    assert turn_ends_in_pauses(timeline, []) is None
    silent = Timeline(caller=timeline.caller, agent_audio=agent_audio())
    assert turn_ends_in_pauses(silent, [{"role": "assistant", "started_speaking_at": 1.0}]) is None
    # A realtime model logs caller turns without the stop time or end-of-turn delay.
    untimed: list[dict[str, Any]] = [
        {"role": "assistant", "started_speaking_at": 1.0},
        {"role": "user", "text": "hi"},
    ]
    assert turn_ends_in_pauses(timeline, untimed) is None
