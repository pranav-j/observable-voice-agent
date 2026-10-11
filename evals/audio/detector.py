"""Speech onset and offset in the agent's received audio.

A deterministic energy detector, run offline over saved audio. The thresholds are fixed
here, recorded in every report, and must not change between runs that are compared.
See docs/adr/0005-audio-eval-measurement.md.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 10
THRESHOLD_DBFS = -45.0
MIN_SPEECH_MS = 30
MIN_SILENCE_MS = 300

DETECTOR_SETTINGS = {
    "sample_rate": SAMPLE_RATE,
    "frame_ms": FRAME_MS,
    "threshold_dbfs": THRESHOLD_DBFS,
    "min_speech_ms": MIN_SPEECH_MS,
    "min_silence_ms": MIN_SILENCE_MS,
}


@dataclass(frozen=True)
class Segment:
    start: float  # seconds from the start of the audio
    end: float


def frame_levels(
    samples: np.ndarray[Any, Any], sample_rate: int = SAMPLE_RATE
) -> np.ndarray[Any, Any]:
    """RMS level of each 10 ms frame, in dBFS (full scale = 0 dB)."""
    frame = sample_rate * FRAME_MS // 1000
    usable = len(samples) - len(samples) % frame
    if usable == 0:
        return np.zeros(0)
    frames = samples[:usable].astype(np.float64).reshape(-1, frame) / 32768.0
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-10))


def speech_segments(samples: np.ndarray[Any, Any], sample_rate: int = SAMPLE_RATE) -> list[Segment]:
    """Speech runs: at least MIN_SPEECH_MS above threshold, ended by MIN_SILENCE_MS below it."""
    speech = frame_levels(samples, sample_rate) > THRESHOLD_DBFS
    min_speech = MIN_SPEECH_MS // FRAME_MS
    min_silence = MIN_SILENCE_MS // FRAME_MS
    seconds = FRAME_MS / 1000

    segments: list[Segment] = []
    i, n = 0, len(speech)
    while i < n:
        if not speech[i : i + min_speech].all() or i + min_speech > n:
            i += 1
            continue
        start = i
        last_speech = i
        j = i
        while j < n and j - last_speech <= min_silence:
            if speech[j]:
                last_speech = j
            j += 1
        segments.append(Segment(start * seconds, (last_speech + 1) * seconds))
        i = last_speech + 1 + min_silence
    return segments


class LiveSpeech:
    """The onset rule above, applied to audio as it streams in, for turn-taking.

    Only a run of at least MIN_SPEECH_MS above threshold counts as speech, so stray loud
    frames (codec comfort noise, clicks) don't look like the agent still talking. Chunks
    can be any length; partial frames carry over to the next call.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.frame = sample_rate * FRAME_MS // 1000
        self.min_run = MIN_SPEECH_MS // FRAME_MS
        self.run = 0
        self.carry = np.zeros(0, dtype=np.int16)

    def feed(self, samples: np.ndarray[Any, Any]) -> bool:
        """True if this chunk contains confirmed speech."""
        data = np.concatenate([self.carry, samples])
        usable = len(data) - len(data) % self.frame
        self.carry = data[usable:]
        confirmed = False
        for loud in frame_levels(data[:usable], self.frame * 1000 // FRAME_MS) > THRESHOLD_DBFS:
            self.run = self.run + 1 if loud else 0
            confirmed = confirmed or self.run >= self.min_run
        return confirmed
