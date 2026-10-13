# Eval report: audio mode

Started 2026-10-13T00:57:25+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 100.0% (18/18 runs) |
| Scenarios passing all runs | 6/6 (100.0%) |
| Order exact match | 100.0% (of 18 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 7 |
| Run duration p50 / p95 (s) | 99.0 / 125.9 |
| Agent tokens in / out | 690,407 / 18,068 |
| Caller tokens in / out | 59,389 / 1,300 |

## By tag

| Tag | Pass |
|---|---|
| correction | 3/3 (100.0%) |
| happy_path | 9/9 (100.0%) |
| hesitation | 6/6 (100.0%) |
| phone | 3/3 (100.0%) |
| quantity | 3/3 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_quantity_change | correction, quantity | 3/3 | 1.00 | agent_ended x3 |
| happy_path_details_upfront | happy_path | 3/3 | 1.00 | agent_ended x3 |
| happy_path_multi_item_modifiers | happy_path | 3/3 | 1.00 | agent_ended x2, caller_ended x1 |
| happy_path_single_coffee | happy_path | 3/3 | 1.00 | agent_ended x1, caller_ended x2 |
| hesitation_pause_mid_order | hesitation | 3/3 | 1.00 | agent_ended x2, caller_ended x1 |
| hesitation_pause_on_phone | hesitation, phone | 3/3 | 1.00 | agent_ended x1, caller_ended x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 3614 / 7732 (75 turns) |
| Dead air (over 2 s) | 57 turns (76.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | not measured |
| WER | 36.4% (726 words) |
| WER, clean | 36.4% (726 words) |
| Agent cost per minute | $0.072 ($2.139 over 29.6 min, 18 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): not recorded.

Agent-side p95 (s): not recorded.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-realtime, pipeline realtime, preemptive_generation True, stt_model gpt-realtime, stt_provider realtime, tts_format mp3, tts_model gpt-realtime, tts_provider realtime, tts_voice marin, turn_detection semantic, vad_min_silence_ms 550.

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

None.

## Rule violations

None.
