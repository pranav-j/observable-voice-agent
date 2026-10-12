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

## Next

Speech moved to local models (Whisper and Kokoro, `docs/adr/0007-local-speech.md`) to cut cost. That's also a latency change in its own right: Kokoro starts speaking in about half the time. The remaining levers get measured on that pipeline against its own baseline, starting with the end-of-turn wait, since Whisper only starts transcribing once the caller has stopped speaking.
