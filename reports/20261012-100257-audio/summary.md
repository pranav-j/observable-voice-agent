# Eval report: audio mode

Started 2026-10-12T10:02:57+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 88.9% (16/18 runs) |
| Scenarios passing all runs | 5/6 (83.3%) |
| Order exact match | 88.9% (of 18 scored runs) |
| Mean field accuracy | 0.95 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 9 |
| Run duration p50 / p95 (s) | 141.7 / 220.4 |
| Agent tokens in / out | 841,307 / 7,610 |
| Caller tokens in / out | 80,569 / 1,573 |

## By tag

| Tag | Pass |
|---|---|
| correction | 3/3 (100.0%) |
| happy_path | 9/9 (100.0%) |
| hesitation | 4/6 (66.7%) |
| phone | 3/3 (100.0%) |
| quantity | 3/3 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| correction_quantity_change | correction, quantity | 3/3 | 1.00 | caller_ended x3 |
| happy_path_details_upfront | happy_path | 3/3 | 1.00 | caller_ended x3 |
| happy_path_multi_item_modifiers | happy_path | 3/3 | 1.00 | caller_ended x3 |
| happy_path_single_coffee | happy_path | 3/3 | 1.00 | caller_ended x3 |
| hesitation_pause_mid_order | hesitation | 1/3 | 0.70 | caller_ended x3 |
| hesitation_pause_on_phone | hesitation, phone | 3/3 | 1.00 | caller_ended x3 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 5251 / 9042 (108 turns) |
| Dead air (over 2 s) | 106 turns (98.1%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 1/6 scripted pauses (16.7%) |
| Turn ended during a scripted pause, agent's clock | 4/6 scripted pauses (66.7%) |
| WER | 16.6% (821 words) |
| WER, clean | 16.6% (821 words) |
| Agent cost per minute | $0.000 ($0.015 over 43.2 min, 18 runs) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.59, llm_node_ttft 1.02, tts_node_ttfb 0.74, e2e_latency 4.20.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, vad_min_silence_ms 300.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 100.0% (2 of 2 tool errors) |
| Tool errors followed by silence (not judged) | 1 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_mid_order** run 1 (caller_ended): customer name: expected 'Deepak', got 'Deepuck'
- **hesitation_pause_mid_order** run 3 (caller_ended): missing: 1x mysore_masala_dosa with extra_butter; missing: 1x masala_chai (regular) with less_sugar; extra: 1x masala_dosa with extra_butter

## Rule violations

None.
