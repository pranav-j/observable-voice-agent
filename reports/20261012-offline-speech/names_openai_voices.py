"""Whisper on short name lines spoken by OpenAI voices, saved by two earlier audio runs."""

import glob
import json
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

NAMES = {"Priya", "Nikhil", "Pooja", "Neha", "Imran", "Tanvi", "Sameer", "Manoj", "Gaurav",
         "Meera", "Ritu", "Kavya", "Anil", "Farhan", "Arjun", "Deepak", "Ananya", "Suresh",
         "Vikram", "Rohit"}
items = []
for rep in ["reports/20261012-001531-audio", "reports/20261012-021611-audio"]:
    for run in glob.glob(rep + "/raw/audio/*/"):
        t = json.load(open(run + "timeline.json"))
        wavs = sorted(Path(run, "caller_lines").glob("*.wav"))
        for u, w in zip(t["caller"], wavs):
            words = u["text"].replace(".", "").replace(",", "").split()
            names = [x for x in words if x in NAMES]
            if names and len(words) <= 4:
                with wave.open(str(w)) as f:
                    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
                x = pcm.astype(np.float32) / 32768
                idx = np.arange(0, len(x), 1.5).astype(int)
                items.append((names[0], x[idx[idx < len(x)]]))
print(len(items), "short name lines spoken by OpenAI voices")
for name in ["base.en", "small.en"]:
    model = WhisperModel(name, device="cpu", compute_type="int8")
    ok = sum(
        n.lower() in " ".join(s.text for s in model.transcribe(a, language="en", beam_size=1)[0]).lower()
        for n, a in items
    )
    print(f"{name}: names right {ok}/{len(items)}")
