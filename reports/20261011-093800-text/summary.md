# Eval report: text mode

Started 2026-10-11T09:38:00+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v1).

## Overall

| Metric | Value |
|---|---|
| Task success | 90.0% (18/20 runs) |
| Scenarios passing all runs | 1/2 (50.0%) |
| Order exact match | 100.0% (of 20 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 3 runs |
| Turns p50 / p95 | 5 / 11 |
| Run duration p50 / p95 (s) | 33.0 / 61.9 |
| Agent tokens in / out | 772,974 / 7,229 |
| Caller tokens in / out | 69,458 / 1,728 |

## By tag

| Tag | Pass |
|---|---|
| phone | 18/20 (90.0%) |
| phone_name | 18/20 (90.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| phone_name_plus91 | phone_name, phone | 8/10 | 1.00 | agent_ended x6, caller_ended x2, caller_gave_up x2 |
| phone_name_spoken_digits | phone_name, phone | 10/10 | 1.00 | agent_ended x3, caller_ended x7 |

## Failures

- **phone_name_plus91** run 3 (caller_gave_up): status: expected confirmed, got abandoned
- **phone_name_plus91** run 5 (caller_gave_up): status: expected confirmed, got abandoned

## Rule violations

- **phone_name_plus91** run 2: confirmed in the same turn as the read-back, before the caller replied (x1)
- **phone_name_plus91** run 6: confirmed in the same turn as the read-back, before the caller replied (x2)
- **phone_name_plus91** run 10: confirmed in the same turn as the read-back, before the caller replied (x1)
