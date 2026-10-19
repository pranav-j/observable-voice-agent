# Phone read-back, as written against digit by digit

Run 2026-10-19 offline. Script: `check.py`, output: `output.txt`.

The same read-back line, synthesized by Kokoro two ways and transcribed by Whisper `base.en`. Whisper writes spoken digits as a number either way, so the thousands commas and the length are what tell the two readings apart. The digit-by-digit reading has no thousands commas and is shorter. The live check in `reports/20261019-053045-audio` came back the second way.
