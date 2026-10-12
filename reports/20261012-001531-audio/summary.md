# Eval report: audio mode

Started 2026-10-12T00:15:31+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 77.8% (14/18 runs) |
| Scenarios passing all runs | 3/6 (50.0%) |
| Order exact match | 83.3% (of 18 scored runs) |
| Mean field accuracy | 0.94 |
| Escalation agreement | 94.4% (1 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 9 |
| Run duration p50 / p95 (s) | 182.6 / 252.3 |
| Agent tokens in / out | 849,034 / 7,652 |
| Caller tokens in / out | 82,961 / 1,699 |

## By tag

| Tag | Pass |
|---|---|
| correction | 3/3 (100.0%) |
| happy_path | 7/9 (77.8%) |
| hesitation | 4/6 (66.7%) |
| phone | 3/3 (100.0%) |
| quantity | 3/3 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_quantity_change | correction, quantity | 3/3 | 1.00 | caller_ended x3 |
| happy_path_details_upfront | happy_path | 3/3 | 1.00 | caller_ended x3 |
| happy_path_multi_item_modifiers | happy_path | 2/3 | 1.00 | agent_ended x1, caller_ended x2 |
| happy_path_single_coffee | happy_path | 2/3 | 0.89 | caller_ended x3 |
| hesitation_pause_mid_order | hesitation | 1/3 | 0.73 | caller_ended x3 |
| hesitation_pause_on_phone | hesitation, phone | 3/3 | 1.00 | caller_ended x3 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 7013 / 14169 (114 turns) |
| Dead air (over 2 s) | 114 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 5/6 scripted pauses (83.3%) |
| WER | 11.6% (929 words) |
| WER, clean | 11.6% (929 words) |
| Agent cost per minute | $0.023 ($1.280 over 55.8 min, 18 runs; includes estimates) |
| Replies with a sentence said twice | 1 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.58, llm_node_ttft 1.50, tts_node_ttfb 1.00, e2e_latency 5.93.

Agent-side p95 (s): end_of_turn_delay 2.50, llm_node_ttft 3.73, tts_node_ttfb 1.33, e2e_latency 14.70.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_format pcm, tts_model gpt-4o-mini-tts, tts_voice coral.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 75.0% (3 of 4 tool errors) |
| Tool errors followed by silence (not judged) | 4 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **happy_path_multi_item_modifiers** run 2 (agent_ended): status: expected confirmed, got abandoned
- **happy_path_single_coffee** run 2 (caller_ended): status: expected confirmed, got escalated; customer: not set
- **hesitation_pause_mid_order** run 2 (caller_ended): missing: 1x mysore_masala_dosa with extra_butter; extra: 1x masala_dosa with extra_butter
- **hesitation_pause_mid_order** run 3 (caller_ended): missing: 1x mysore_masala_dosa with extra_butter; extra: 1x masala_dosa with extra_butter

## Rule violations

None.
