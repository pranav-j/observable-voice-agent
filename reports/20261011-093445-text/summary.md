# Eval report: text mode

Started 2026-10-11T09:34:45+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v1).

## Overall

| Metric | Value |
|---|---|
| Task success | 100.0% (20/20 runs) |
| Scenarios passing all runs | 2/2 (100.0%) |
| Order exact match | 100.0% (of 20 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 6 |
| Run duration p50 / p95 (s) | 32.2 / 50.2 |
| Agent tokens in / out | 632,956 / 6,081 |
| Caller tokens in / out | 61,211 / 1,490 |

## By tag

| Tag | Pass |
|---|---|
| phone | 20/20 (100.0%) |
| phone_name | 20/20 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| phone_name_plus91 | phone_name, phone | 10/10 | 1.00 | agent_ended x5, caller_ended x5 |
| phone_name_spoken_digits | phone_name, phone | 10/10 | 1.00 | agent_ended x1, caller_ended x9 |

## Failures

None.

## Rule violations

None.
