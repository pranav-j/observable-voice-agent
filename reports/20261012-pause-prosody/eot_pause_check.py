"""Run from the repo root: `.venv/bin/python reports/20261012-pause-prosody/eot_pause_check.py`.

Offline: what LiveKit's local end-of-turn model hears at a scripted pause.

old  = first half synthesized on its own (the harness until now)
cut  = whole line synthesized once, pause cut in by evals.audio.caller.pause_point
end  = the real end of the whole line (control: should look finished)
"""

import json
import sys
from pathlib import Path

import numpy as np
from livekit.local_inference import EOT

sys.path.insert(0, ".")
from evals.audio.caller import (  # noqa: E402
    SPEAK_RATE,
    _kokoro_create,
    pause_point,
    speakable,
    split_for_pause,
    to_pcm16,
)
from evals.runner import load_kokoro  # noqa: E402

RATE = 16000
SILENCE_AT_PREDICT = 0.2  # LiveKit asks the model once 200 ms of silence has built up


def tts(kokoro, text, voice):
    audio, rate = _kokoro_create(kokoro, speakable(text), voice, 0.9)
    assert rate == SPEAK_RATE
    return np.asarray(audio, dtype=np.float64)


def to16k(x):
    n = int(len(x) * RATE / SPEAK_RATE)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def frame_energy(x, frame):
    n = len(x) // frame
    return np.sqrt((x[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)


def prob(model, speech):
    """The model's input when LiveKit asks: the last 1.2 s, ending 200 ms into silence."""
    x = np.concatenate([speech, np.zeros(int(SPEAK_RATE * SILENCE_AT_PREDICT))])
    pcm = to_pcm16(to16k(x))[-int(1.2 * RATE) :]
    return float(model.predict(pcm))


def main():
    lines = set()
    for tl in Path("reports").glob("2026101*-audio/raw/audio/*hesitation*/timeline.json"):
        for u in json.loads(tl.read_text())["caller"]:
            if u["pauses"]:
                lines.add(u["text"])
    lines = sorted(lines)
    kokoro = load_kokoro(Path("models/kokoro"))
    model = EOT()
    voices = ["hf_alpha", "hm_omega", "bf_emma"]
    rows = []
    for text in lines:
        first, _ = split_for_pause(text)
        for voice in voices:
            whole = tts(kokoro, text, voice)
            old = tts(kokoro, first, voice)
            c = pause_point(whole, text, first)
            rows.append((text, voice, prob(model, old), prob(model, whole[:c]), prob(model, whole)))
    for text, voice, o, c, e in rows:
        print(f"{o:5.2f} {c:5.2f} {e:5.2f}  {voice:9s} {text[:60]}")
    a = np.array([r[2:] for r in rows])
    print(f"\n{len(rows)} lines x voices. mean p(end of turn): old {a[:,0].mean():.2f}  cut {a[:,1].mean():.2f}  real end {a[:,2].mean():.2f}")
    print(f"above LiveKit's 0.36 threshold: old {(a[:,0]>=0.36).sum()}/{len(a)}  cut {(a[:,1]>=0.36).sum()}/{len(a)}  real end {(a[:,2]>=0.36).sum()}/{len(a)}")


if __name__ == "__main__":
    main()
