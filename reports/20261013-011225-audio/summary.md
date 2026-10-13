# Eval report: audio mode

Started 2026-10-13T01:12:25+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 33.3% (6/18 runs) |
| Scenarios passing all runs | 0/6 (0.0%) |
| Order exact match | 88.9% (of 18 scored runs) |
| Mean field accuracy | 0.97 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 12 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 6 / 12 |
| Run duration p50 / p95 (s) | 152.1 / 281.1 |
| Agent tokens in / out | 908,180 / 31,557 |
| Caller tokens in / out | 99,794 / 1,906 |

## By tag

| Tag | Pass |
|---|---|
| correction | 1/3 (33.3%) |
| happy_path | 1/9 (11.1%) |
| hesitation | 4/6 (66.7%) |
| phone | 2/3 (66.7%) |
| quantity | 1/3 (33.3%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_quantity_change | correction, quantity | 1/3 | 0.94 | caller_ended x1, caller_hung_up_early x2 |
| happy_path_details_upfront | happy_path | 0/3 | 1.00 | caller_hung_up_early x3 |
| happy_path_multi_item_modifiers | happy_path | 0/3 | 1.00 | caller_hung_up_early x3 |
| happy_path_single_coffee | happy_path | 1/3 | 0.89 | caller_ended x1, caller_hung_up_early x2 |
| hesitation_pause_mid_order | hesitation | 2/3 | 1.00 | caller_ended x2, caller_hung_up_early x1 |
| hesitation_pause_on_phone | hesitation, phone | 2/3 | 1.00 | caller_ended x2, caller_hung_up_early x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 3186 / 6885 (129 turns) |
| Dead air (over 2 s) | 99 turns (76.7%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 3/6 scripted pauses (50.0%) |
| Turn ended during a scripted pause, agent's clock | not measured |
| WER | 33.6% (1077 words) |
| WER, clean | 33.6% (1077 words) |
| Agent cost per minute | $0.018 ($0.903 over 51.5 min, 18 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): not recorded.

Agent-side p95 (s): not recorded.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-realtime-mini, pipeline realtime, preemptive_generation True, stt_model gpt-realtime-mini, stt_provider realtime, tts_format mp3, tts_model gpt-realtime-mini, tts_provider realtime, tts_voice marin, turn_detection semantic, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 87.5% (7 of 8 tool errors) |
| Tool errors followed by silence (not judged) | 0 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **correction_quantity_change** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; 3x veg_biryani (half): got quantity 2
- **correction_quantity_change** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_details_upfront** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_details_upfront** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_details_upfront** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_multi_item_modifiers** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_multi_item_modifiers** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_multi_item_modifiers** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_single_coffee** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned; customer: not set
- **happy_path_single_coffee** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned
- **hesitation_pause_mid_order** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned
- **hesitation_pause_on_phone** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

None.
