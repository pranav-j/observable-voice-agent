"""Kokoro synthesis time for typical agent sentences, idle machine, three tries each."""

import time

from kokoro_onnx import Kokoro

k = Kokoro("models/kokoro/kokoro-v1.0.onnx", "models/kokoro/voices-v1.0.bin")
k.create("Warm up.", voice="af_heart", speed=1.0, lang="en-us")
for text in ["What name should I put on the order?", "Got it.", "Let me read that back.",
             "One large Cold Coffee with oat milk.", "Your total is 280 rupees."]:
    ts = []
    for _ in range(3):
        t = time.perf_counter()
        audio, sr = k.create(text, voice="af_heart", speed=1.0, lang="en-us")
        ts.append(time.perf_counter() - t)
    print(f"{min(ts):.2f}-{max(ts):.2f}s for {len(audio) / sr:.1f}s of audio | {text}")
