"""Background noise for audio scenarios, generated from a seed, and mixing at a set SNR.

Clips are procedural, not recordings: our own work, released CC0, reproducible bit for
bit. See data/noise/SOURCES.md. A clip name like "cafe_02" means kind "cafe", seed 2.

Levels: caller speech is normalized to SPEECH_DBFS, and the noise bed sits snr_db below
it for the whole call, including the caller's silences, as real background noise would.
"""

from functools import cache
from typing import Any

import numpy as np

SAMPLE_RATE = 24_000  # matches the caller's text-to-speech output
SPEECH_DBFS = -23.0
CLIP_SECONDS = 60.0  # long enough that a loop isn't noticeable within one utterance

Array = np.ndarray[Any, Any]


def rms_dbfs(x: Array) -> float:
    """Level of a float signal (full scale = 1.0) in dBFS."""
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    return float(20 * np.log10(max(rms, 1e-10)))


def to_dbfs(x: Array, dbfs: float) -> Array:
    current = rms_dbfs(x)
    return x * 10 ** ((dbfs - current) / 20) if current > -200 else x


def _colored(rng: np.random.Generator, n: int, exponent: float) -> Array:
    """Noise with power falling as 1/f^exponent: 0 white, 1 pink, 2 brown."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    freqs[0] = freqs[1]
    signal = np.fft.irfft(spectrum / freqs ** (exponent / 2), n)
    return signal / np.std(signal)


def _bandpass(x: Array, low: float, high: float) -> Array:
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SAMPLE_RATE)
    spectrum[(freqs < low) | (freqs > high)] = 0
    return np.fft.irfft(spectrum, len(x))


def _cafe(rng: np.random.Generator, n: int) -> Array:
    t = np.arange(n) / SAMPLE_RATE
    babble = np.zeros(n)
    for _ in range(6):  # several overlapping "talkers": speech-band noise, syllable-rate swings
        rate = rng.uniform(3.0, 5.5)
        envelope = 0.5 + 0.5 * np.sin(2 * np.pi * rate * t + rng.uniform(0, 2 * np.pi)) ** 2
        babble += _bandpass(rng.standard_normal(n), 300, 3400) * envelope
    floor = _colored(rng, n, 1.0) * 0.4
    clatter = np.zeros(n)
    for start in rng.integers(0, n - 2400, size=int(CLIP_SECONDS * 0.8)):  # dishes, cutlery
        click = rng.standard_normal(2400) * np.exp(-np.arange(2400) / 300)
        clatter[start : start + 2400] += click * rng.uniform(0.5, 2.0)
    return babble / np.std(babble) + floor + _bandpass(clatter, 2000, 8000)


def _street(rng: np.random.Generator, n: int) -> Array:
    t = np.arange(n) / SAMPLE_RATE
    rumble = _colored(rng, n, 2.0)
    swells = np.zeros(n)
    for center in rng.uniform(0, CLIP_SECONDS, size=8):  # passing cars
        swells += np.exp(-(((t - center) / rng.uniform(1.0, 2.5)) ** 2))
    return rumble * (0.6 + swells) + _colored(rng, n, 1.0) * 0.3


KINDS = {"cafe": _cafe, "street": _street}


@cache
def noise_clip(name: str) -> Array:
    """A float clip at unit RMS. "cafe_02" is kind "cafe" generated from seed 2."""
    kind, _, seed = name.rpartition("_")
    if kind not in KINDS or not seed.isdigit():
        raise ValueError(
            f"unknown noise clip {name!r}; expected one of {sorted(KINDS)} plus _<seed>"
        )
    n = int(SAMPLE_RATE * CLIP_SECONDS)
    signal = KINDS[kind](np.random.default_rng(int(seed)), n)
    return to_dbfs(signal, 0.0)


def noise_bed(name: str, snr_db: float, n_samples: int, offset: int = 0) -> Array:
    """`n_samples` of the clip, looped, at SNR_db below caller speech level."""
    clip = noise_clip(name)
    idx = (np.arange(n_samples) + offset) % len(clip)
    return to_dbfs(clip, SPEECH_DBFS - snr_db)[idx]


def speech_at_level(pcm16: Array) -> Array:
    """Text-to-speech output (int16) as float, normalized to SPEECH_DBFS."""
    return to_dbfs(pcm16.astype(np.float64) / 32768.0, SPEECH_DBFS)


def to_pcm16(x: Array) -> Array:
    return np.asarray(np.clip(x, -1.0, 1.0) * 32767, dtype=np.int16)
