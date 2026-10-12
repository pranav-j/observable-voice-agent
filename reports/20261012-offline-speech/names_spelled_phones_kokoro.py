"""Which local Whisper setup hears Indian names, spelled names and phone numbers?

Kokoro speaks test lines in the six caller voices; each Whisper variant transcribes them;
each line is scored the way the agent would use it: the name, the joined spelling, the
ten digits. Everything runs locally.
"""

import re
import sys
import time

import numpy as np
from faster_whisper import WhisperModel

from evals.audio.caller import KOKORO_VOICE_POOL, speakable
from evals.runner import load_kokoro
from pathlib import Path
from voice_order.order.state import spelled_name, spoken_digits

NAMES = ["Priya", "Nikhil", "Pooja", "Neha", "Imran", "Tanvi", "Sameer", "Manoj", "Gaurav",
         "Meera", "Ritu", "Kavya", "Anil", "Farhan", "Arjun", "Deepak", "Ananya", "Suresh"]
PHONES = ["9876523456", "9876538270", "9876514142", "9876552914", "9876526457", "9876569314"]
PROMPT = "Indian names, sometimes spelled letter by letter, and 10-digit phone numbers."

kokoro = load_kokoro(Path("models/kokoro"))
voices = list(KOKORO_VOICE_POOL.values())
lines = []  # (kind, expected, audio16k)
for i, name in enumerate(NAMES):
    voice = voices[i % len(voices)]
    for kind, text in [
        ("name", f"It's {name}."),
        ("spelled", f"It's spelled {'-'.join(name.upper())}."),
    ]:
        audio, rate = kokoro.create(speakable(text), voice=voice, speed=1.0, lang="en-us")
        x = np.asarray(audio, dtype=np.float32)
        idx = np.arange(0, len(x), rate / 16000).astype(int)
        lines.append((kind, name, np.concatenate([np.zeros(3200, np.float32), x[idx[idx < len(x)]]])))
for i, phone in enumerate(PHONES * 2):
    voice = voices[i % len(voices)]
    audio, rate = kokoro.create(speakable(f"My number is {phone}."), voice=voice, speed=1.0, lang="en-us")
    x = np.asarray(audio, dtype=np.float32)
    idx = np.arange(0, len(x), rate / 16000).astype(int)
    lines.append(("phone", phone, np.concatenate([np.zeros(3200, np.float32), x[idx[idx < len(x)]]])))
print(f"{len(lines)} lines")


def score(kind: str, expected: str, heard: str) -> bool:
    if kind == "phone":
        return expected in spoken_digits(heard)
    if kind == "spelled":
        letters = re.sub(r"(?i)^.*?spelled\s*", "", heard).strip(" .")
        joined = spelled_name(letters) or letters.replace(" ", "")
        return joined.lower() == expected.lower()
    return expected.lower() in heard.lower()


for name in sys.argv[1:] or ["base.en", "small.en", "base", "small"]:
    model = WhisperModel(name, device="cpu", compute_type="int8")
    for prompt in [None, PROMPT]:
        ok = {"name": 0, "spelled": 0, "phone": 0}
        total = {"name": 0, "spelled": 0, "phone": 0}
        times = []
        for kind, expected, audio in lines:
            t0 = time.perf_counter()
            segs, _ = model.transcribe(audio, language="en", beam_size=1, initial_prompt=prompt)
            heard = " ".join(s.text for s in segs)
            times.append(time.perf_counter() - t0)
            total[kind] += 1
            ok[kind] += score(kind, expected, heard)
        times.sort()
        print(
            f"{name:>9} prompt={'yes' if prompt else 'no ':3} | names {ok['name']}/{total['name']} "
            f"spelled {ok['spelled']}/{total['spelled']} phones {ok['phone']}/{total['phone']} "
            f"| p50 {times[len(times) // 2]:.2f}s",
            flush=True,
        )
