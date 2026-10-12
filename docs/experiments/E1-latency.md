# E1: Latency, one change at a time

## Setup

- **Question:** what makes the agent answer sooner, measured the way a caller experiences it?
- **Primary metric:** caller-side response latency, from the end of the caller's speech to the start of the agent's audio, measured from the audio the simulated caller received (see `docs/adr/0005-audio-eval-measurement.md`). Reported at p50 and p95.
- **Supporting metrics:** the agent's own per-stage timings. These are end-of-turn delay, the LLM's time to first token, text-to-speech time to first audio, and the agent's end-to-end figure. They don't measure the caller's experience, but they show *which* stage a change moved. Task success shows whether a change broke anything.
- **Scenarios:** six scenarios that exercise tool calls and pauses, at three runs each, so 18 calls per configuration. They are `happy_path_single_coffee`, `happy_path_multi_item_modifiers`, `happy_path_details_upfront`, `correction_quantity_change`, `hesitation_pause_mid_order` and `hesitation_pause_on_phone`.
- **Starting point:** the first full audio baseline (`reports/20261011-163931-audio`), restricted to those six scenarios. That means OpenAI for recognition, LLM and voice, a 500 ms end-of-turn wait, preemptive generation off, and two calls at a time.
- **Method:** each lever is compared against the configuration before it, and kept only if it helps without breaking anything. Comparisons come from `make compare BEFORE=... AFTER=... ONLY=<the six scenarios>`.

## Results

### Lever 1: raw PCM audio from text-to-speech instead of MP3 (kept)

Report: `reports/20261012-001531-audio`, compared with the baseline.

| Metric | Before | After |
|---|---|---|
| Response latency p50 / p95 (ms) | 6861 / 10444 | 7013 / 14169 |
| Text-to-speech first audio, p50 (s) | 1.088 | 1.005 |
| LLM first token, p50 (s) | 1.201 | 1.504 |
| Task success | 0.944 | 0.778 |

The change did what it was meant to: the agent's voice started about 80 ms sooner. The caller-side number didn't improve, because in the same run the LLM's first token arrived 300 ms later. That's provider-side variation between hours, which this change doesn't touch, and it was bigger than the gain. Task success moved within the run-to-run noise of 18 calls: two of the four failures were the same Mysore-versus-plain masala dosa mix-up. Kept, as a small and certain gain at no cost.

### Lever 2: filler phrases when a reply needs tool calls (rejected)

Report: `reports/20261012-021611-audio`, compared with lever 1.

| Metric | Before | After |
|---|---|---|
| Response latency p50 / p95 (ms) | 7013 / 14169 | 4232 / 6610 |
| Task success | 0.778 | 0.389 |
| Replies with a sentence said twice | 1 | 5 |
| End-of-turn delay, p50 (s) | 0.578 | 0.969 |

On latency alone this looks like the biggest win, but it isn't one. The metric times the start of the agent's audio, and the filler ("One moment.") *is* that start: the real answer came no sooner. Worse, the simulated caller answered the filler ("Sure."), its reply became a turn of its own, and the agent then answered twice or lost track. Task success halved. A real caller saying "okay" would cause the same thing, so this is a property of the design, not of the test. Rejected.

## Interpretation so far

- On this pipeline, the agent's own end-to-end time is about 5.6 seconds at p50. Most of it is LLM round trips: each step takes over a second to its first token, and a turn with tool calls needs two or three steps. Speech synthesis adds about a second, and the end of turn about half a second.
- Caller-side latency is noisy between runs at different hours, because the hosted LLM's speed varies by more than most single changes save. Per-stage timings separate a change's effect from that noise.
- A latency metric based on the start of audio rewards saying *anything* early. Any lever that adds early speech needs task success and doubled replies checked alongside it.

## Limitations

- Eighteen calls per configuration is enough to see large effects and stage timings, but not small changes in task success.
- Runs happened at different hours, so provider speed differed between them. That's partly why stage timings carry the interpretation here.
- Region co-location wasn't tried: everything ran from one laptop against OpenAI's public endpoints.
- Preemptive generation wasn't measured, because the budget ran out. Doubled replies were later traced to split caller turns rather than to preemptive generation, so it deserves a fair measurement.

## On local speech

Speech moved to local models (`docs/adr/0007-local-speech.md`), mainly to cut cost. That move is a latency change of its own. Over the full suite, it took caller-side latency from 6756 to 4885 ms at p50 and from 10284 to 8761 ms at p95, at the same task success of 85/93 (`reports/20261011-163931-audio` against `reports/20261012-072648-audio`). The agent code also improved between those two runs. The voice now starts in 0.69 s instead of 1.10 s at p50. The end of turn got slower, from 0.58 to 0.88 s, because Whisper transcribes only after voice detection decides the caller has stopped.

The remaining levers were measured on that pipeline, against a fresh run of the same six scenarios on the same code. That run was `reports/20261012-093814-audio`: 18/18 passed, at 5106 / 8483 ms.

### Lever 3: a shorter end-of-speech silence for voice detection, 550 → 300 ms (rejected)

Report: `reports/20261012-100257-audio`.

| Metric | Before | After |
|---|---|---|
| Response latency p50 / p95 (ms) | 5106 / 8483 | 5251 / 9042 |
| End-of-turn delay, p50 (s) | 0.882 | 0.593 |
| False cut-offs | 0 of 6 pauses | 1 of 6 pauses |
| Task success | 18/18 | 16/18 |

The agent's own end of turn got 0.3 s faster, but callers didn't get answers any sooner, and the agent started answering into a caller's mid-sentence pause. This is also the first run where `false_cutoff_rate` moved. With replies this fast, an early answer finally lands inside the pause, which partly answers the open item in `docs/harness-validation.md`. Rejected.

### Lever 4: preemptive generation (kept)

Report: `reports/20261012-102638-audio`.

| Metric | Before | After |
|---|---|---|
| Response latency p50 / p95 (ms) | 5106 / 8483 | 4761 / 7157 |
| Task success | 18/18 | 17/18 |
| Replies with a sentence said twice | 0 | 1 |

It's a real gain, especially at p95. The one failure is the Mysore-versus-plain masala dosa mix-up, which happens without preemptive generation too. One doubled reply in 18 calls is about the rate seen with it off: 3 in 93 in the full local run. That fits doubling coming from split caller turns, not from this setting. Kept, and on by default.

## Where it stands

| Configuration | Report | Response latency p50 / p95 (ms) |
|---|---|---|
| Start: hosted speech, MP3 | `20261011-163931-audio`, six scenarios | 6861 / 10444 |
| Local speech, same code as lever 3 and 4 | `20261012-093814-audio` | 5106 / 8483 |
| Local speech plus preemptive generation | `20261012-102638-audio` | 4761 / 7157 |

That's about 2.1 s off the median and 3.3 s off p95 for these scenarios. Every turn is still over two seconds, which counts as dead air. What's left is mostly LLM round trips: each step takes about a second to its first token, and a turn with tool calls needs two or three of them. The next real gains would come from fewer steps per turn, for example by letting the model add an item without searching first, or from a faster LLM. Neither has been tried yet.
