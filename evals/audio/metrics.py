"""Caller-side audio metrics, as pure functions over a call's timeline.

All times are seconds on the caller's monotonic clock. Caller speech boundaries are
known (the caller generated them). Agent speech comes from the fixed onset detector run
over the audio the caller received. See docs/adr/0005-audio-eval-measurement.md.
"""

import re
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np

from evals.audio.detector import SAMPLE_RATE, Segment, speech_segments

DEAD_AIR_SECONDS = 2.0
# Agent speech with gaps shorter than this is one reply: the pauses between its sentences.
# After a real stop, the next reply can't start this soon (end of turn plus an LLM call).
SAME_REPLY_GAP_SECONDS = 1.5
TRANSCRIPT_GRACE_SECONDS = 4.0  # the agent's transcript of a caller line can arrive after it ends


@dataclass(frozen=True)
class CallerUtterance:
    text: str
    start: float
    end: float
    pauses: tuple[tuple[float, float], ...] = ()  # scripted silences inside the utterance
    interrupt: bool = False  # spoken over the agent on purpose


@dataclass
class Timeline:
    caller: list[CallerUtterance] = field(default_factory=list)
    agent_audio: np.ndarray[Any, Any] = field(default_factory=lambda: np.zeros(0, dtype=np.int16))
    agent_audio_start: float = 0.0  # clock time of the first received agent sample
    heard_caller: list[tuple[float, str]] = field(default_factory=list)  # agent's STT of the caller

    def agent_speech(self) -> list[Segment]:
        offset = self.agent_audio_start
        return [
            Segment(s.start + offset, s.end + offset)
            for s in speech_segments(self.agent_audio, SAMPLE_RATE)
        ]


def response_latencies(timeline: Timeline) -> list[float]:
    """Seconds from the end of each regular caller utterance to the agent's next speech onset.

    Utterances the agent answered only after the caller spoke again get no value.
    """
    speech = timeline.agent_speech()
    starts = [u.start for u in timeline.caller]
    latencies = []
    for i, u in enumerate(timeline.caller):
        if u.interrupt:
            continue
        next_start = starts[i + 1] if i + 1 < len(starts) else float("inf")
        onset = next((s.start for s in speech if u.end <= s.start < next_start), None)
        if onset is not None:
            latencies.append(onset - u.end)
    return latencies


def speech_runs(segments: list[Segment], gap: float = SAME_REPLY_GAP_SECONDS) -> list[Segment]:
    """Join segments separated by less than `gap` seconds into one run of speech."""
    runs: list[Segment] = []
    for s in segments:
        if runs and s.start - runs[-1].end < gap:
            runs[-1] = Segment(runs[-1].start, s.end)
        else:
            runs.append(s)
    return runs


def barge_in_stop_times(timeline: Timeline) -> list[float]:
    """For interruptions made while the agent was speaking: caller onset to agent silence.

    Silence means the end of the agent's reply, not of its current sentence: an agent that
    ignores the caller pauses between sentences and carries on.
    """
    runs = speech_runs(timeline.agent_speech())
    stops = []
    for u in timeline.caller:
        if not u.interrupt:
            continue
        talking = next((r for r in runs if r.start <= u.start < r.end), None)
        if talking is not None:
            stops.append(talking.end - u.start)
    return stops


def false_cutoffs(timeline: Timeline) -> tuple[int, int]:
    """(pauses where the agent started talking before the caller finished, total pauses).

    A reply to a premature end of turn usually arrives after a short pause has ended, while
    the caller is finishing the sentence, so the window runs from the pause to the
    utterance's end, not just the pause itself.
    """
    speech = timeline.agent_speech()
    cut, total = 0, 0
    for u in timeline.caller:
        for pause_start, _ in u.pauses:
            total += 1
            if any(pause_start <= s.start < u.end for s in speech):
                cut += 1
    return cut, total


_DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def normalize_words(text: str) -> list[str]:
    """Lowercase words without punctuation, with digits spelled out one by one."""
    text = re.sub(r"\d", lambda m: f" {_DIGITS[int(m.group())]} ", text.lower())
    return re.findall(r"[a-z']+", text)


def word_errors(reference: list[str], hypothesis: list[str]) -> int:
    """Levenshtein distance over words: substitutions + insertions + deletions."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        current = [i]
        for j, hyp in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref != hyp)))
        previous = current
    return previous[-1]


def utterance_wer(timeline: Timeline) -> list[tuple[int, int]]:
    """(word errors, reference words) per caller utterance, against what the agent heard."""
    results = []
    for u in timeline.caller:
        reference = normalize_words(u.text)
        if not reference:
            continue
        heard = " ".join(
            text
            for t, text in timeline.heard_caller
            if u.start <= t <= u.end + TRANSCRIPT_GRACE_SECONDS
        )
        results.append((word_errors(reference, normalize_words(heard)), len(reference)))
    return results


def audio_metrics(timeline: Timeline) -> dict[str, Any]:
    latencies = response_latencies(timeline)
    stops = barge_in_stop_times(timeline)
    cut, pauses = false_cutoffs(timeline)
    wer = utterance_wer(timeline)
    errors, words = sum(e for e, _ in wer), sum(n for _, n in wer)
    return {
        "response_latencies_ms": [round(x * 1000) for x in latencies],
        "dead_air_turns": sum(x > DEAD_AIR_SECONDS for x in latencies),
        "barge_in_stop_ms": [round(x * 1000) for x in stops],
        "false_cutoffs": cut,
        "scripted_pauses": pauses,
        "wer_errors": errors,
        "wer_words": words,
    }


# --- real calls: both sides from the worker's two-channel recording ---------------------------


def recording_metrics(caller: list[Segment], agent: list[Segment]) -> dict[str, Any]:
    """Timing for a real call, where nothing was scripted and both sides are detected.

    Response latency runs from the end of the caller's speech to the agent's next onset,
    when the last thing before that onset was the caller (not the agent's own previous
    sentence) and the caller wasn't still talking. Barge-in stop runs from caller speech
    starting while the agent talks to the end of that agent segment. Short backchannels
    ("mm-hmm") count as barge-ins too; nothing here knows what was said.
    """
    latencies: list[float] = []
    for a in agent:
        if any(c.start < a.start < c.end for c in caller):
            continue  # the agent started over the caller
        before = [(s.end, "caller") for s in caller if s.end <= a.start]
        before += [(s.end, "agent") for s in agent if s.end <= a.start]
        if before:
            end, who = max(before)
            if who == "caller":
                latencies.append(a.start - end)
    runs = speech_runs(agent)
    stops = [
        next(a.end - c.start for a in runs if a.start < c.start < a.end)
        for c in caller
        if any(a.start < c.start < a.end for a in runs)
    ]
    return {
        "response_latencies_ms": [round(x * 1000) for x in latencies],
        "dead_air_turns": sum(x > DEAD_AIR_SECONDS for x in latencies),
        "barge_in_stop_ms": [round(x * 1000) for x in stops],
        "false_cutoffs": 0,  # needs scripted pauses
        "scripted_pauses": 0,
        "wer_errors": 0,  # needs a script of what the caller said
        "wer_words": 0,
    }


def doubled_replies(agent_messages: list[str]) -> int:
    """Agent messages that say the same sentence twice in a row.

    Seen with preemptive generation on: "May I have your name?May I have your name?".
    Counted from the agent's own record of what it said.
    """
    count = 0
    for text in agent_messages:
        sentences = [s.strip().lower() for s in re.findall(r"[^.?!]+[.?!]?", text) if s.strip()]
        if any(a == b and len(a) > 3 for a, b in pairwise(sentences)):
            count += 1
    return count
