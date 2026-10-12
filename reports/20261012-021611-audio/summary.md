# Eval report: audio mode

Started 2026-10-12T02:16:11+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 38.9% (7/18 runs) |
| Scenarios passing all runs | 0/6 (0.0%) |
| Order exact match | 66.7% (of 18 scored runs) |
| Mean field accuracy | 0.91 |
| Escalation agreement | 77.8% (4 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 5 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 11 / 16 |
| Run duration p50 / p95 (s) | 232.7 / 315.7 |
| Agent tokens in / out | 1,231,077 / 11,254 |
| Caller tokens in / out | 148,470 / 2,543 |

## By tag

| Tag | Pass |
|---|---|
| correction | 1/3 (33.3%) |
| happy_path | 4/9 (44.4%) |
| hesitation | 2/6 (33.3%) |
| phone | 1/3 (33.3%) |
| quantity | 1/3 (33.3%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_quantity_change | correction, quantity | 1/3 | 0.94 | caller_ended x1, caller_hung_up_early x1, transferred x1 |
| happy_path_details_upfront | happy_path | 2/3 | 1.00 | caller_ended x2, caller_gave_up x1 |
| happy_path_multi_item_modifiers | happy_path | 1/3 | 0.86 | caller_ended x2, caller_hung_up_early x1 |
| happy_path_single_coffee | happy_path | 1/3 | 0.89 | caller_ended x1, caller_hung_up_early x1, transferred x1 |
| hesitation_pause_mid_order | hesitation | 1/3 | 0.80 | caller_ended x1, caller_hung_up_early x1, transferred x1 |
| hesitation_pause_on_phone | hesitation, phone | 1/3 | 0.94 | caller_ended x1, caller_hung_up_early x1, transferred x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4232 / 6610 (192 turns) |
| Dead air (over 2 s) | 190 turns (99.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| WER | 12.6% (1294 words) |
| WER, clean | 12.6% (1294 words) |
| Agent cost per minute | $0.024 ($1.534 over 63.9 min, 18 runs; includes estimates) |
| Replies with a sentence said twice | 5 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.97, llm_node_ttft 1.20, tts_node_ttfb 0.99, e2e_latency 3.69.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases True, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_format pcm, tts_model gpt-4o-mini-tts, tts_voice coral.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 62.5% (5 of 8 tool errors) |
| Tool errors followed by silence (not judged) | 4 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **correction_quantity_change** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **correction_quantity_change** run 3 (transferred): status: expected confirmed, got escalated; 3x veg_biryani (half): got quantity 2
- **happy_path_details_upfront** run 2 (caller_gave_up): status: expected confirmed, got abandoned
- **happy_path_multi_item_modifiers** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned; customer: not set
- **happy_path_multi_item_modifiers** run 3 (caller_ended): missing: 1x butter_naan
- **happy_path_single_coffee** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_single_coffee** run 3 (transferred): status: expected confirmed, got escalated; customer: not set
- **hesitation_pause_mid_order** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned
- **hesitation_pause_mid_order** run 3 (transferred): status: expected confirmed, got escalated; missing: 1x mysore_masala_dosa with extra_butter; extra: 1x masala_dosa with extra_butter; customer: not set
- **hesitation_pause_on_phone** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; customer name: expected 'Ritu', got 'Retu'
- **hesitation_pause_on_phone** run 2 (transferred): status: expected confirmed, got escalated

## Rule violations

None.
