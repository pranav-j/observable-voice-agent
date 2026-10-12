"""Stage 1: is local Whisper good and fast enough, on the caller lines we already have?

For each saved caller line (the exact audio the simulated caller sent), transcribe it
with faster-whisper and score it against the line's script. Compare with what OpenAI's
recognizer heard on the same calls (the agent's transcripts, via the harness's WER).
"""

import glob
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from evals.audio.metrics import normalize_words, word_errors
from evals.rescore import timeline_from
from evals.audio.metrics import utterance_wer

models = sys.argv[1:] or ["base.en", "small.en"]
runs = sorted(glob.glob("reports/2026101*-audio/raw/audio/*/caller_lines"))
lines: list[tuple[str, np.ndarray]] = []
openai_err = openai_words = 0
for folder in runs:
    run = Path(folder).parent
    saved = json.loads((run / "timeline.json").read_text())
    texts = [u["text"] for u in saved["caller"]]
    wavs = sorted(Path(folder).glob("*.wav"))
    for text, wav in zip(texts, wavs, strict=False):
        with wave.open(str(wav)) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        # 24 kHz -> 16 kHz for Whisper
        x = pcm.astype(np.float32) / 32768
        idx = np.arange(0, len(x), 1.5).astype(int)
        lines.append((text, x[idx[idx < len(x)]]))
    for e, n in utterance_wer(timeline_from(run)):
        openai_err += e
        openai_words += n
print(f"{len(lines)} caller lines from {len(runs)} calls")
print(f"OpenAI (gpt-live-transcribe, as the agent heard it): WER {openai_err / max(openai_words, 1):.1%} over {openai_words} words")

for name in models:
    model = WhisperModel(name, device="cpu", compute_type="int8")
    model.transcribe(lines[0][1], language="en")  # warm up
    errors = words = 0
    times = []
    for text, audio in lines:
        t0 = time.perf_counter()
        segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=False)
        heard = " ".join(s.text for s in segments)
        times.append(time.perf_counter() - t0)
        ref = normalize_words(text)
        e, n = word_errors(ref, normalize_words(heard)), len(ref)
        errors += e
        words += n
    times.sort()
    print(
        f"{name:>18}: WER {errors / words:.1%} over {words} words | "
        f"time per line p50 {times[len(times) // 2]:.2f}s p90 {times[int(len(times) * 0.9)]:.2f}s"
    )
