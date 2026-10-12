# E4: Speech-to-text on noisy calls, hosted against local

## Setup

- **Question:** does the choice of speech recognizer matter for getting orders right when the line is noisy? And do differences in word error rate show up as wrong orders?
- **Recognizers:**
  - Hosted: OpenAI `gpt-live-transcribe`, streaming.
  - Local: Whisper `base.en` through `faster-whisper`, on the CPU, transcribing each utterance once voice detection says it has ended.
- **Runs:** the two full audio baselines, one per recognizer. Both used OpenAI voices for the simulated caller, and both ran two calls at a time.
  - Hosted: `reports/20261011-163931-audio`.
  - Local: `reports/20261012-072648-audio`. That run also used Kokoro for the agent's voice.
- **Scenarios with noise mixed in:** `noise_accent_cafe_heavy` (café noise at 5 dB SNR) and `noise_accent_misheard_names` (street noise at 10 dB). `noise_accent_hinglish` is reported alongside: it has no noise but a heavy accent. Each scenario ran three times per recognizer.
- **Word error rate:** the caller's scripted words against what the agent's recognizer heard, per utterance, with digits normalized (see `docs/adr/0005-audio-eval-measurement.md`). Exact match is the order-level result: the final order equals the expected one.

## Results

Word error rate by noise level, over each whole suite:

| Noise | Hosted | Local |
|---|---|---|
| None | 11.9% (4553 words) | 15.2% (4652 words) |
| 15 dB | 6.7% (164 words) | 12.7% (110 words) |
| 10 dB | 15.3% (150 words) | 22.8% (215 words) |
| 5 dB | 11.8% (93 words) | 7.7% (117 words) |

The three noise and accent scenarios, nine runs per recognizer:

| | Hosted | Local |
|---|---|---|
| Word error rate | 16.0% | 17.9% |
| Orders exactly right | 8 of 9 | 9 of 9 |

## Interpretation

- **Words:** local Whisper got somewhat more words wrong than the hosted recognizer, on clean calls and at 10 and 15 dB. The 5 dB result goes the other way, but it rests on about a hundred words per side, so it doesn't settle anything.
- **Orders:** the extra word errors didn't become order errors. Exact match on the noisy scenarios was 8 of 9 hosted and 9 of 9 local, and the full suites tied at 85 of 93. Most of what a recognizer gets wrong is words the order doesn't depend on. When it does matter, as with a misheard name, a number or a size, the read-back and the caller's correction usually catch it. That loop was built for exactly this.
- **Where recognition does fail orders,** it's names and long digit runs, not noise as such. The local pipeline's real failures were names, and the offline checks in `reports/20261012-offline-speech` show `small.en` hearing names better than `base.en`, at about four times the latency.

## Limitations

- Nine runs per recognizer on the noisy scenarios is small. A difference of one order is noise.
- The noise is procedural (`evals/audio/noise.py`), not recorded from real cafés or streets, and only two SNR levels are covered by noisy scenarios.
- The two runs differ in more than the recognizer: the agent's voice (OpenAI against Kokoro) and a few agent fixes changed between them. Word error rate depends only on what the caller sent and what the recognizer heard, so it's the cleaner comparison of the two. Exact match is affected by everything.
- Only two recognizers were compared, and only one local model size was run in a live suite.
