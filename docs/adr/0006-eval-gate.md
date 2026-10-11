# 0006: Gating changes on eval results

- **Status:** accepted
- **Date:** 2026-10-11

## Context

Unit tests catch broken code, but not a prompt tweak that makes the agent worse at taking orders, or a pipeline change that adds half a second to every reply. Those only show up in the evals. For the evals to stop a bad change, CI needs a pass/fail rule over a report.

Eval results are noisy. The same build, run twice, doesn't give the same pass rate, because the agent and the simulated caller are both LLMs. A rule that ignores that will fail at random, and a gate that fails at random gets ignored.

## Decision

- **Baseline.** `evals/baseline.json` holds the key metrics of one reviewed report per mode (text and audio). It changes only by running `make baseline REPORT=...` after reading that report, and the file records which report it came from.
- **Margins.** `evals/gate.yaml` gives each gated metric a margin in one of three forms. An absolute drop for rates where higher is better (task success). A relative increase for timings where lower is better (p95 latency). An absolute rise for rates where lower is better (false cut-offs, word error rate). A report fails if any metric is worse than its baseline by more than the margin.
- **Missing metrics are skipped, and named.** If one side didn't measure a metric (a run with no barge-ins has no barge-in timing), the check is reported as skipped. It never passes silently.
- **Margins start provisional.** They're set above the run-to-run spread seen so far, and they get tightened as repeat runs of the same build show how big that spread really is.
- **Where it runs.** Every push gets lint, types and unit tests. Pull requests also get the text suite plus the gate, but only when the API key secret is present, so forks without secrets still get a green check for the parts they can run. The audio suite plus the gate runs on manual dispatch, because it needs a LiveKit server and a running worker, and it costs real money.

## Alternatives

- **Statistical tests per metric** (for example, a significance test on pass rates). More principled, but with a few dozen scenarios and a few runs each, it would rarely say anything with confidence, and it's harder to read in a CI log. Plain margins are easy to reason about and easy to tune.
- **Absolute thresholds** ("task success at least 90%"). Simple, but they say nothing about whether a change made things worse, and they would need moving every time the suite gets harder.
- **Gating on every metric.** Turn counts and call duration move for harmless reasons, like a chattier but correct reply. Only metrics that mean "worse for the caller" are gated.

## Consequences

- A change that really costs a few points of pass rate can slip under a margin. That's the price of not failing at random. Repeat runs narrow it over time.
- The baseline has to be refreshed deliberately when the agent improves, or later regressions are measured against an outdated bar.
- Seeded faults (`FAULT=...`) are the check that the margins aren't so loose that real breakage gets through.
