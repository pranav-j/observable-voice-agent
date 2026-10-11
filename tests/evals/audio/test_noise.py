"""Procedural noise: deterministic, at the right level, and mixed at the right SNR."""

import numpy as np
import pytest
from evals.audio.noise import (
    SAMPLE_RATE,
    SPEECH_DBFS,
    noise_bed,
    noise_clip,
    rms_dbfs,
    speech_at_level,
    to_pcm16,
)


def test_same_name_gives_identical_audio() -> None:
    assert np.array_equal(noise_clip("cafe_01"), noise_clip("cafe_01"))


def test_different_seeds_differ() -> None:
    assert not np.array_equal(noise_clip("cafe_01")[:1000], noise_clip("cafe_02")[:1000])


@pytest.mark.parametrize("name", ["cafe_01", "street_01"])
def test_clips_are_at_unit_level(name: str) -> None:
    assert rms_dbfs(noise_clip(name)) == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("snr", [5.0, 15.0, 25.0])
def test_noise_bed_sits_snr_below_speech(snr: float) -> None:
    bed = noise_bed("cafe_01", snr, SAMPLE_RATE * 5)
    assert rms_dbfs(bed) == pytest.approx(SPEECH_DBFS - snr, abs=0.5)


def test_speech_is_normalized() -> None:
    t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    pcm = (np.sin(2 * np.pi * 200 * t) * 3000).astype(np.int16)
    assert rms_dbfs(speech_at_level(pcm)) == pytest.approx(SPEECH_DBFS, abs=0.1)


def test_bed_loops_past_the_clip_end() -> None:
    clip_len = len(noise_clip("street_01"))
    assert len(noise_bed("street_01", 10.0, 1000, offset=clip_len - 500)) == 1000


def test_pcm16_conversion_clips_instead_of_wrapping() -> None:
    assert to_pcm16(np.array([2.0, -2.0, 0.5])).tolist() == [32767, -32767, 16383]


def test_unknown_clip_names_fail() -> None:
    with pytest.raises(ValueError, match="unknown noise clip"):
        noise_clip("rain_01")
