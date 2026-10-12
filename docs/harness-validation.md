# Harness validation

An eval harness is only worth trusting if it fails when the agent is broken. To check that, the voice worker can be broken on purpose with the `FAULT` setting, one fault at a time (`src/voice_order/agent/faults.py`). Each fault should push its own metric well past the gate margin in `evals/gate.yaml`.

## Setup

- **Baseline:** `reports/20261011-163931-audio`, the full audio suite with no fault. Three runs per scenario, two calls at a time.
- **Fault runs:** the same build with one fault switched on. Two runs per scenario, on the scenarios that exercise that fault.
- Each comparison uses only the baseline runs for those same scenarios: `make compare BEFORE=<baseline> AFTER=<fault run> ONLY=<scenarios>`.
- Every report records the worker's settings, including the fault, so the "Agent config" line in each `summary.md` shows what it ran against.
- All reports below were re-scored with the current metric definitions (see "What validation changed").

## Results

| Fault | Report | Scenarios | Its metric: baseline → fault | Gate margin | Caught? |
|---|---|---|---|---|---|
| `no_barge_in` | `20261011-190542-audio` | `barge_in_*`, `readback_barge_in_size_change` | Barge-in stop p95: 1151 → 18996 ms. p50: 912 → 16895 ms | +25% | Yes |
| `drop_modifiers` | `20261011-191919-audio` | three scenarios with modifiers | Order exact match: 1.000 → 0.000 | −6 points (text), −10 (audio task success) | Yes |
| `aggressive_eou` | `20261012-000238-audio` | `hesitation_*` | False cut-off rate: 0.000 → 0.000. Task success: 0.889 → 0.333 | +0.15 absolute | By task success, not by its own metric |
| `slow_llm` | `20261011-234245-audio` | `happy_path_*` | Response latency p95: 10014 → 14433 ms (+44%) | +15% | Yes |

Other effects worth knowing about:
- **`no_barge_in`** also dropped task success from 0.833 to 0.250. An agent that talks over a correction misses it.
- **`slow_llm`** added about 1.7 s at p50, not 0.8 s. A turn with tool calls runs the LLM two or three times, and each run pays the delay.
- **`drop_modifiers`** shows a p95 latency spike (32670 ms). That's a side effect of the agent struggling with orders that won't come out right, not part of the fault.

## What validation changed

**The barge-in metric was wrong.** The first version measured from the caller's interruption to the end of the agent's *current speech segment*. Segments end at every pause between sentences, so an agent that ignored the caller simply finished its sentence, paused, and carried on. The metric measured that pause and reported a *faster* stop, 917 → 207 ms. The fault looked like an improvement.

The metric now runs to the end of the agent's reply: speech less than 1.5 s apart counts as one reply. The baseline and every fault report were re-scored from their saved audio with `python -m evals.rescore`, with no new calls. With the old rule removed, the fault is caught by a wide margin. Runs where the agent does stop barely changed: baseline p50 went from 917 to 912 ms.

**The first `aggressive_eou` fault was too weak.** It only cut the end-of-turn silence to 150 ms (report `20261011-233140-audio`). The agent uses a semantic turn detector that holds the turn when a sentence sounds unfinished, so nothing broke: task success even went up, 0.889 → 1.000. That speaks well for the turn detector but proves nothing about the harness. The fault now also drops the turn model and ends turns on voice activity alone.

## Still open

**`false_cutoff_rate` can't see cut-offs while replies are this slow.** It counts scripted pauses during which agent *audio* starts. With the stronger fault, the agent did commit turns in the middle of the caller's sentence, which is why orders came out wrong. But its replies take about 6 seconds to start, so the audio began after the caller had already finished. The damage shows up in task success and exact match, not in this metric. The metric only becomes sensitive once replies are faster than a pause, so it needs re-checking after the latency work. An agent-side measure, such as "turn committed during a scripted pause", would catch it regardless of speed.
