"""Run from the repo root: `.venv/bin/python reports/20261019-readback-digits/check.py`.

The agent's phone read-back, synthesized by Kokoro as written and with digits spaced out
(src/voice_order/agent/spoken_digits.py), then transcribed by Whisper base.en. Whisper writes
spoken digits as a number either way, so the thousands commas and the length tell the two
readings apart.
"""

import numpy as np
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro

from voice_order.agent.spoken_digits import digits_one_by_one

k = Kokoro("models/kokoro/kokoro-v1.0.onnx", "models/kokoro/voices-v1.0.bin")
m = WhisperModel("base.en", device="cpu", compute_type="int8")
text = "Your number is 98765 23456. Is that right?"
for label, t in [("as written", text), ("digits spaced", digits_one_by_one(text))]:
    audio, rate = k.create(t, voice="af_heart", speed=1.0, lang="en-us")
    x = np.arange(len(audio))
    a16 = np.interp(np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate)), x, audio)
    heard = " ".join(s.text.strip() for s in m.transcribe(a16.astype(np.float32), beam_size=1)[0])
    print(f"{label}: {len(audio) / rate:.1f}s, Kokoro said: {t!r}, Whisper heard: {heard!r}")
