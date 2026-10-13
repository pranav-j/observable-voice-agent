# E2: Cascade against speech-to-speech

## Setup

- **Question:** does one speech-to-speech model, which hears the caller's audio and answers in audio, beat the cascade on latency, and what does it cost in correctness and money?
- **Cascade (the default):** local Whisper `base.en` hears the caller, LiveKit's turn detector decides when the turn is over, `gpt-6-luna` decides what to do and calls the tools, and local Kokoro speaks. Preemptive generation is on.
- **Speech-to-speech:** OpenAI's realtime model, selected with `PIPELINE=realtime` (`src/voice_order/agent/worker.py`). It gets the same instructions and the same tools, and every order change still goes through them. It does its own turn-taking (OpenAI's server-side semantic voice detection) and transcribes the caller with `gpt-4o-mini-transcribe` for the transcript.
- **What differs besides the model:**
  - Fixed lines like the greeting are spoken by asking the model to say them, since it has no separate voice to read text with.
  - One tool guard is off. In the cascade, a tool that should wait for the caller's answer refuses to run in the same step as a question to the caller. That guard reads the text of the step as it streams, which a realtime model doesn't expose the same way. The core rules still hold: no confirmation without a read-back the caller heard, and no confirmation before the caller replies to it.
- **Scenarios:** the six from the latency experiment, three runs each. Those are `happy_path_single_coffee`, `happy_path_multi_item_modifiers`, `happy_path_details_upfront`, `correction_quantity_change`, `hesitation_pause_mid_order` and `hesitation_pause_on_phone`. The cascade side comes from the full confirmation run, restricted to the same scenarios with `make compare ... ONLY=`.
- **Models:** `gpt-realtime` and the cheaper `gpt-realtime-mini`, each on all 18 calls.
- **Caller:** OpenAI voices, as in the baselines.
- **Cost:** from the usage LiveKit reports, priced in `config/rates.yaml`. Realtime models price audio tokens separately and much higher than text, and the usage accounting prices the two apart.

## Results

The cascade figures are the six scenarios' share of the full confirmation run, `reports/20261012-224542-audio`, from `make compare ... ONLY=<the six>`. That run predates the fix for repeated sentences.

| Metric | Cascade | `gpt-realtime` | `gpt-realtime-mini` |
|---|---|---|---|
| Report | `20261012-224542-audio` (6 of its scenarios) | `20261013-005725-audio` | `20261013-011225-audio` |
| Task success | 17/18 (0.944) | 18/18 (1.000) | 6/18 (0.333) |
| Order exact match | 0.944 | 1.000 | 0.889 |
| Caller hung up mid-order | 0 runs | 0 runs | 12 runs |
| Response latency p50 / p95 (ms) | 4538 / 7664 | 3614 / 7732 | 3186 / 6885 |
| Turns with over 2 s of dead air | 97.2% | 76.0% | 76.7% |
| Replies with a sentence said twice | 3 | 0 | 0 |
| Agent cost per minute | $0.0004 | $0.072 | $0.018 |

## Interpretation

- **`gpt-realtime` was faster at the median and got every order right.** It answered 0.9 s sooner at p50, and a quarter of its turns came in under two seconds, against almost none for the cascade. It also passed all 18 calls.
- **The slowest turns didn't get faster.** p95 stayed at about 7.7 seconds. I haven't traced which turns those are. Turns with tool calls are the likely ones, since a tool call is still a round trip whichever model makes it.
- **It costs about 180 times as much.** $0.072 a minute against $0.0004, because speech-to-speech prices audio tokens, and the cascade's speech runs on the worker's own CPU. Even next to hosted speech in the cascade, $0.024 a minute in `20261011-163931-audio`, it's three times the price.
- **`gpt-realtime-mini` is the cheap option, and it failed most calls.** It often read the order back in its own words instead of fetching and reading the tool's read-back, then tried to confirm. The code refuses to confirm without the real read-back, so those orders were never placed, and the caller gave up. Not one call placed a wrong order. The guard turned a model that ignores the flow into abandoned orders instead of wrong ones.
- **Decision:** keep the cascade as the default. At this project's scale the cost difference outweighs a 0.9 s median gain. For a service where latency matters more than cost, `gpt-realtime` is the better pipeline, and `PIPELINE=realtime` switches to it.

## Limitations

- 18 calls per configuration, on six scenarios, one run each.
- The cascade figures come from a run made at a different hour, and provider speed changes from hour to hour.
- Word error rate isn't comparable. For the realtime model it measures OpenAI's side transcription of the caller, which the model doesn't act on and which often arrives later than the harness's window for matching it to a line.
- The split-sentence count needs turn timings that the realtime model doesn't log, so it's "not measured" for those runs.
- The realtime cost includes an estimate: LiveKit reports the side transcription without a duration, so it's priced on the whole call's length, which overstates it.
- Only OpenAI's speech-to-speech models were tried.
