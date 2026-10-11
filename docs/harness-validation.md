# Harness validation

An eval harness is only worth trusting if it fails when the agent is broken. To check that, the voice worker can be broken on purpose with the `FAULT` setting, one fault at a time. Each fault has to push one metric clearly past where a normal run lands. If it doesn't, the harness is blind to that failure.

## Status

**Not run yet.** The seeded faults are in the code (`src/voice_order/agent/faults.py`), but the validation runs haven't happened. The first full audio run stopped partway through when the API account ran out of credit. There are no results below until those runs happen.

## The faults

| Fault | What breaks | Scenarios | Metric that has to move |
|---|---|---|---|
| `no_barge_in` | The agent keeps talking when the caller speaks over it | `barge_in_*`, `readback_barge_in_size_change` | Barge-in stop p50 / p95 |
| `drop_modifiers` | The voice tool layer quietly drops modifiers from add and update | `happy_path_single_coffee`, `happy_path_multi_item_modifiers`, `correction_swap_modifier` | Order exact match |
| `aggressive_eou` | End-of-turn silence cut to 150 ms | `hesitation_*` | False cut-off rate |
| `slow_llm` | 800 ms added before the LLM's first token | `happy_path_*` | Response latency p95 |

The core (menu, order, tools) is never touched. The faults live in the voice layer, and every call saves the worker's settings, including the fault, next to its recording, so a report always says what it ran against.

## How to run it

For each fault, run the same scenarios twice: once with no fault and once with it, with the same number of runs and the same concurrency.

```
FAULT=none make worker          # in one terminal
make eval MODE=audio SCENARIOS="barge_in_*,readback_barge_in_size_change" RUNS=3 ARGS=--yes

FAULT=no_barge_in make worker   # restart the worker with the fault
make eval MODE=audio SCENARIOS="barge_in_*,readback_barge_in_size_change" RUNS=3 ARGS=--yes
```

Then compare the metric in the two reports' `summary.md`. The report's "Agent config" line confirms which fault each run had.

## Results

None yet.
