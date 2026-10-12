# Eval report: audio mode

Started 2026-10-12T14:07:00+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 77.8% (7/9 runs) |
| Scenarios passing all runs | 2/3 (66.7%) |
| Order exact match | 77.8% (of 9 scored runs) |
| Mean field accuracy | 0.93 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 8 / 13 |
| Run duration p50 / p95 (s) | 190.2 / 277.1 |
| Agent tokens in / out | 565,202 / 4,457 |
| Caller tokens in / out | 61,496 / 1,305 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 7/9 (77.8%) |
| phone | 3/3 (100.0%) |
| price_question | 3/3 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 1/3 | 0.80 | caller_ended x2, caller_gave_up x1 |
| hesitation_pause_on_phone | hesitation, phone | 3/3 | 1.00 | caller_ended x3 |
| hesitation_undecided_drink | hesitation, price_question | 3/3 | 1.00 | caller_ended x3 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4990 / 8507 (75 turns) |
| Dead air (over 2 s) | 75 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/9 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 9/9 scripted pauses (100.0%) |
| WER | 21.0% (696 words) |
| WER, clean | 21.0% (696 words) |
| Agent cost per minute | $0.000 ($0.010 over 29.5 min, 9 runs) |
| Replies with a sentence said twice | 1 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.91, llm_node_ttft 1.11, tts_node_ttfb 0.92, e2e_latency 5.03.

Agent-side p95 (s): end_of_turn_delay 1.27, llm_node_ttft 1.87, tts_node_ttfb 2.05, e2e_latency 8.60.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 300, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection vad, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 100.0% (3 of 3 tool errors) |
| Tool errors followed by silence (not judged) | 1 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_mid_order** run 1 (caller_gave_up): status: expected confirmed, got abandoned; customer: not set
- **hesitation_pause_mid_order** run 3 (caller_ended): missing: 1x mysore_masala_dosa with extra_butter; extra: 1x masala_dosa with extra_butter

## Rule violations

None.
