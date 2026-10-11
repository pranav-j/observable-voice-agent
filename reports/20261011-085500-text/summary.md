# Eval report: text mode

Started 2026-10-11T08:55:00+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v1).

## Overall

| Metric | Value |
|---|---|
| Task success | 50.0% (10/20 runs) |
| Scenarios passing all runs | 0/2 (0.0%) |
| Order exact match | 80.0% (of 20 scored runs) |
| Mean field accuracy | 0.93 |
| Escalation agreement | 95.0% (1 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 4 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 7 runs |
| Turns p50 / p95 | 5 / 7 |
| Run duration p50 / p95 (s) | 30.4 / 47.9 |
| Agent tokens in / out | 712,395 / 7,239 |
| Caller tokens in / out | 58,879 / 1,518 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 4/10 (40.0%) |
| out_of_stock | 6/10 (60.0%) |
| plural_search | 6/10 (60.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_details_upfront | happy_path | 4/10 | 0.87 | agent_ended x7, caller_ended x1, caller_gave_up x1, caller_hung_up_early x1 |
| unknown_item_plural_samosas | out_of_stock, plural_search | 6/10 | 1.00 | agent_ended x3, caller_ended x3, caller_hung_up_early x3, transferred x1 |

## Failures

- **happy_path_details_upfront** run 1 (caller_ended): missing: 1x veg_samosa
- **happy_path_details_upfront** run 4 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_details_upfront** run 6 (agent_ended): missing: 1x veg_samosa
- **happy_path_details_upfront** run 7 (agent_ended): missing: 1x veg_samosa
- **happy_path_details_upfront** run 8 (caller_gave_up): status: expected confirmed, got abandoned
- **happy_path_details_upfront** run 10 (agent_ended): 1x veg_samosa: got quantity 2
- **unknown_item_plural_samosas** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **unknown_item_plural_samosas** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **unknown_item_plural_samosas** run 7 (transferred): status: expected confirmed, got escalated
- **unknown_item_plural_samosas** run 8 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

- **happy_path_details_upfront** run 2: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 3: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 5: confirmed in the same turn as the read-back, before the caller replied (x2)
- **happy_path_details_upfront** run 7: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 8: confirmed in the same turn as the read-back, before the caller replied (x2)
- **happy_path_details_upfront** run 9: confirmed in the same turn as the read-back, before the caller replied (x1)
- **happy_path_details_upfront** run 10: confirmed in the same turn as the read-back, before the caller replied (x2)
