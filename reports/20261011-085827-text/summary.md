# Eval report: text mode

Started 2026-10-11T08:58:27+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v1).

## Overall

| Metric | Value |
|---|---|
| Task success | 75.0% (15/20 runs) |
| Scenarios passing all runs | 0/2 (0.0%) |
| Order exact match | 85.0% (of 20 scored runs) |
| Mean field accuracy | 0.97 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 3 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 6 runs |
| Turns p50 / p95 | 5 / 6 |
| Run duration p50 / p95 (s) | 31.7 / 43.1 |
| Agent tokens in / out | 619,756 / 6,352 |
| Caller tokens in / out | 53,138 / 1,343 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 8/10 (80.0%) |
| out_of_stock | 7/10 (70.0%) |
| plural_search | 7/10 (70.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_details_upfront | happy_path | 8/10 | 0.95 | agent_ended x6, caller_ended x3, caller_hung_up_early x1 |
| unknown_item_plural_samosas | out_of_stock, plural_search | 7/10 | 0.98 | agent_ended x1, caller_ended x7, caller_hung_up_early x2 |

## Failures

- **happy_path_details_upfront** run 4 (agent_ended): 1x veg_samosa: got quantity 2
- **happy_path_details_upfront** run 9 (caller_hung_up_early): status: expected confirmed, got abandoned; missing: 1x veg_samosa
- **unknown_item_plural_samosas** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **unknown_item_plural_samosas** run 5 (caller_ended): 2x veg_samosa: got quantity 4
- **unknown_item_plural_samosas** run 8 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

- **happy_path_details_upfront** run 2: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 4: confirmed in the same turn as the read-back, before the caller replied (x2)
- **happy_path_details_upfront** run 7: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 9: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 10: confirmed in the same turn as the read-back, before the caller replied (x1)
- **unknown_item_plural_samosas** run 10: confirmed in the same turn as the read-back, before the caller replied (x1)
