# Eval report: audio mode

Started 2026-10-11T19:19:19+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 0.0% (0/6 runs) |
| Scenarios passing all runs | 0/3 (0.0%) |
| Order exact match | 0.0% (of 6 scored runs) |
| Mean field accuracy | 0.22 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 1 |
| Caller hung up mid-order | 2 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 2 / 7 |
| Run duration p50 / p95 (s) | 110.4 / 190.3 |
| Agent tokens in / out | 54,718 / 663 |
| Caller tokens in / out | 13,420 / 325 |

## By tag

| Tag | Pass |
|---|---|
| correction | 0/2 (0.0%) |
| happy_path | 0/4 (0.0%) |
| modifier | 0/2 (0.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_swap_modifier | correction, modifier | 0/2 | 0.67 | caller_gave_up x1, caller_hung_up_early x1 |
| happy_path_multi_item_modifiers | happy_path | 0/2 | 0.00 | caller_hung_up_early x1, error x1 |
| happy_path_single_coffee | happy_path | 0/2 | 0.00 | agent_ended x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 6637 / 32670 (14 turns) |
| Dead air (over 2 s) | 12 turns (85.7%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| Turn ended during a scripted pause, agent's clock | 0/0 scripted pauses (n/a) |
| WER | 53.4% (189 words) |
| WER, clean | 53.4% (189 words) |
| Agent cost per minute | $0.017 ($5.119 over 298.9 min, 5 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.58, llm_node_ttft 1.01, tts_node_ttfb 1.11, e2e_latency 5.12.

Agent-side p95 (s): end_of_turn_delay 2.50, llm_node_ttft 1.35, tts_node_ttfb 31.48, e2e_latency 7.05.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: unknown; agent_prompt_version v1, eou_silence_ms 500, fault drop_modifiers, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_model gpt-4o-mini-tts, tts_voice coral.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | n/a (0 of 0 tool errors) |
| Tool errors followed by silence (not judged) | 0 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **correction_swap_modifier** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; missing: 1x cafe_latte (small) with hazelnut_syrup; extra: 1x cafe_latte (small)
- **correction_swap_modifier** run 2 (caller_gave_up): status: expected confirmed, got abandoned; missing: 1x cafe_latte (small) with hazelnut_syrup; extra: 1x cafe_latte (small); customer: not set
- **happy_path_multi_item_modifiers** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; missing: 1x cappuccino (medium) with oat_milk; missing: 1x masala_dosa with cheese; missing: 1x butter_naan; customer: not set
- **happy_path_multi_item_modifiers** run 2 (error): ConnectError: engine: signal failure: client error: 401 Unauthorized - invalid authorization token: token has invalid claims: token is not valid yet
- **happy_path_single_coffee** run 1 (agent_ended): status: expected confirmed, got abandoned; missing: 1x cold_coffee (large) with oat_milk; customer: not set
- **happy_path_single_coffee** run 2 (agent_ended): status: expected confirmed, got abandoned; missing: 1x cold_coffee (large) with oat_milk; customer: not set

## Rule violations

None.
