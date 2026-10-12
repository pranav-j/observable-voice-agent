# Eval report: audio mode

Started 2026-10-12T15:09:56+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 66.7% (6/9 runs) |
| Scenarios passing all runs | 1/3 (33.3%) |
| Order exact match | 66.7% (of 9 scored runs) |
| Mean field accuracy | 0.92 |
| Escalation agreement | 77.8% (2 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 1 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 8 / 11 |
| Run duration p50 / p95 (s) | 204.9 / 281.3 |
| Agent tokens in / out | 605,951 / 4,461 |
| Caller tokens in / out | 56,399 / 1,261 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 6/9 (66.7%) |
| phone | 3/3 (100.0%) |
| price_question | 2/3 (66.7%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 1/3 | 0.87 | caller_ended x2, transferred x1 |
| hesitation_pause_on_phone | hesitation, phone | 3/3 | 1.00 | caller_ended x3 |
| hesitation_undecided_drink | hesitation, price_question | 2/3 | 0.89 | caller_ended x2, caller_hung_up_early x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4799 / 7953 (67 turns) |
| Dead air (over 2 s) | 67 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/9 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 9/9 scripted pauses (100.0%) |
| WER | 18.5% (685 words) |
| WER, clean | 18.5% (685 words) |
| Agent cost per minute | $0.000 ($0.010 over 26.4 min, 9 runs) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.91, llm_node_ttft 1.10, tts_node_ttfb 0.71, e2e_latency 4.87.

Agent-side p95 (s): end_of_turn_delay 1.15, llm_node_ttft 1.70, tts_node_ttfb 2.10, e2e_latency 8.05.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 300, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection vad, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 0.0% (0 of 1 tool errors) |
| Tool errors followed by silence (not judged) | 1 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_mid_order** run 2 (caller_ended): status: expected confirmed, got escalated; customer: not set
- **hesitation_pause_mid_order** run 3 (transferred): status: expected confirmed, got escalated; customer: not set
- **hesitation_undecided_drink** run 3 (caller_hung_up_early): status: expected confirmed, got abandoned; customer: not set

## Rule violations

None.
