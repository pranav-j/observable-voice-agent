# Offline speech benchmarks, 2026-10-12

Local checks run before and while moving speech to local models. They aren't eval suite runs: no agent, no LiveKit, nothing billed. The scripts here reproduce each result. Run them from the repository root with `PYTHONPATH=.`, after `make models`.

Machine: Apple M4, 24 GB. Whisper ran through `faster-whisper` 1.2.1 on the CPU (int8, `beam_size=1`, `language="en"`), and Kokoro through `kokoro-onnx` 0.6.1.

## Whisper on saved caller lines (`whisper_on_caller_lines.py`)

That's 521 caller lines from 70 audio calls, each the exact audio the simulated caller sent (OpenAI voices, speech only, no noise mixed in). Each transcript was scored against the line's script with the harness's word error rate.

```
521 caller lines from 70 calls
OpenAI (gpt-live-transcribe, as the agent heard it): WER 15.4% over 4302 words
           base.en: WER 12.8% over 4302 words | time per line p50 0.35s p90 0.48s
          small.en: WER 10.9% over 4302 words | time per line p50 1.44s p90 1.69s
```

The hosted figure is what the agent heard on the live calls, after the network and with noise where the scenario had it. Whisper heard the clean audio as sent. So this favours Whisper, and it shows only that local recognition is in the same range.

## Names, spelled names and phone numbers in Kokoro voices (`names_spelled_phones_kokoro.py`)

Kokoro spoke 18 names, the same 18 spelled letter by letter, and 12 phone numbers, rotating through the six caller voices. A line counts as right if the name, the joined spelling or the ten digits come out exactly.

```
48 lines
  base.en prompt=no  | names 7/18 spelled 10/18 phones 12/12 | p50 0.29s
  base.en prompt=yes | names 7/18 spelled 10/18 phones 12/12 | p50 0.30s
 small.en prompt=no  | names 6/18 spelled 11/18 phones 12/12 | p50 1.31s
 small.en prompt=yes | names 5/18 spelled 11/18 phones 12/12 | p50 1.81s
     base prompt=no  | names 9/18 spelled 6/18 phones 4/12 | p50 0.33s
     base prompt=yes | names 10/18 spelled 5/18 phones 4/12 | p50 0.34s
    small prompt=no  | names 6/18 spelled 11/18 phones 12/12 | p50 1.01s
    small prompt=yes | names 7/18 spelled 11/18 phones 12/12 | p50 1.34s
```

## Names spoken by OpenAI voices (`names_openai_voices.py`)

These are short caller lines containing a name, saved by the runs in `reports/20261012-001531-audio` and `reports/20261012-021611-audio`.

```
21 short name lines spoken by OpenAI voices
base.en: names right 16/21
small.en: names right 19/21
```

The same recognizer gets far more names right when an OpenAI voice says them than when a Kokoro voice does, so Kokoro's pronunciation of Indian names was much of the problem.

## Kokoro synthesis time (`kokoro_timing.py`)

```
0.47-0.48s for 1.8s of audio | What name should I put on the order?
0.29-0.33s for 0.8s of audio | Got it.
0.42-0.44s for 1.3s of audio | Let me read that back.
0.73-0.74s for 2.2s of audio | One large Cold Coffee with oat milk.
0.75-0.78s for 2.2s of audio | Your total is 280 rupees.
```
