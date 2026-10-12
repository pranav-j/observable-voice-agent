# Offline check: does a scripted pause sound like the end of a turn?

Run 2026-10-12 on a laptop CPU, no API calls. Script: `eot_pause_check.py`, full output: `output.txt`.

## Why

In the audio runs, the agent ended the caller's turn during most scripted mid-sentence pauses, even with LiveKit's turn detector on. The traces showed the detector had run and rated the half-sentence as finished. That detector (`turn-detector-v1-mini`, run locally through `livekit-local-inference` 0.2.7) listens to the audio, not the words.

Until now the simulated caller synthesized the two halves of a paused line separately and played them with silence between. A half synthesized on its own ends with the intonation of a finished sentence.

## What was run

- **Lines:** every caller line that had a scripted pause in the saved hesitation runs, 41 lines, each in three Kokoro caller voices (`hf_alpha`, `hm_omega`, `bf_emma`) at the hesitant speed. That's 123 cases.
- **Model input:** what LiveKit gives the model when 200 ms of silence has built up after speech: the last 1.2 s of 16 kHz audio. No WebRTC codec in between.
- **Three versions of each case:**
  - **old:** the first half synthesized on its own, then silence. What the harness did.
  - **cut:** the whole line synthesized once, with the pause cut in by `pause_point` in `evals/audio/caller.py`. What the harness does now.
  - **real end:** the whole line, then silence. A control: this one is finished.
- **Threshold:** 0.36, the English threshold recorded in the live runs' traces. Below it, LiveKit waits longer before ending the turn.

## Results

| | Mean end-of-turn probability | Rated finished (≥ 0.36) |
|---|---|---|
| old | 0.34 | 52 of 123 |
| cut | 0.23 | 17 of 123 |
| real end | 0.49 | 86 of 123 |

## Reading it

- Cutting the pause out of one continuous line takes the pauses that sound finished from 52 to 17 of 123. The old harness made the agent's turn detector look much worse at holding a turn than it is.
- The detector isn't sure about real ends either: 37 of 123 rated unfinished. Most of those, 23 of 37, are lines ending in a phone number, which it rates low whether finished or not.
- Kokoro voices only. The live runs that showed the problem mostly used OpenAI's voices, which weren't checked offline because they cost money per line.
- Without the WebRTC codec and at one fixed moment in the silence, these numbers approximate what the live detector sees. They aren't the same measurement.
