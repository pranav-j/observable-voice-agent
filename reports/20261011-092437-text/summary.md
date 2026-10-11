# Eval report: text mode

Started 2026-10-11T09:24:37+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v1).

## Overall

| Metric | Value |
|---|---|
| Task success | 95.0% (19/20 runs) |
| Scenarios passing all runs | 1/2 (50.0%) |
| Order exact match | 100.0% (of 20 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 1 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 7 runs |
| Turns p50 / p95 | 6 / 6 |
| Run duration p50 / p95 (s) | 31.8 / 47.4 |
| Agent tokens in / out | 702,870 / 7,097 |
| Caller tokens in / out | 58,128 / 1,441 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 9/10 (90.0%) |
| out_of_stock | 10/10 (100.0%) |
| plural_search | 10/10 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_details_upfront | happy_path | 9/10 | 1.00 | agent_ended x7, caller_ended x2, caller_hung_up_early x1 |
| unknown_item_plural_samosas | out_of_stock, plural_search | 10/10 | 1.00 | agent_ended x5, caller_ended x5 |

## Failures

- **happy_path_details_upfront** run 10 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

- **happy_path_details_upfront** run 3: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 5: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 6: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 7: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 9: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 10: confirmed in the same turn as the read-back, before the caller replied (x1)
- **unknown_item_plural_samosas** run 1: confirmed in the same turn as the read-back, before the caller replied (x1)
