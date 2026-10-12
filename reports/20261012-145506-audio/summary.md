# Eval report: audio mode

Started 2026-10-12T14:55:06+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 55.6% (5/9 runs) |
| Scenarios passing all runs | 0/3 (0.0%) |
| Order exact match | 55.6% (of 9 scored runs) |
| Mean field accuracy | 0.86 |
| Escalation agreement | 66.7% (3 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 1 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 7 / 11 |
| Run duration p50 / p95 (s) | 186.3 / 271.1 |
| Agent tokens in / out | 483,448 / 3,909 |
| Caller tokens in / out | 54,179 / 1,180 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 5/9 (55.6%) |
| phone | 1/3 (33.3%) |
| price_question | 2/3 (66.7%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 2/3 | 0.80 | caller_ended x3 |
| hesitation_pause_on_phone | hesitation, phone | 1/3 | 0.89 | caller_ended x2, caller_hung_up_early x1 |
| hesitation_undecided_drink | hesitation, price_question | 2/3 | 0.89 | caller_ended x3 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4949 / 8687 (65 turns) |
| Dead air (over 2 s) | 65 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/9 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 0/9 scripted pauses (0.0%) |
| WER | 21.7% (659 words) |
| WER, clean | 21.7% (659 words) |
| Agent cost per minute | $0.000 ($0.009 over 26.3 min, 9 runs) |
| Replies with a sentence said twice | 1 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.95, llm_node_ttft 1.10, tts_node_ttfb 0.81, e2e_latency 4.89.

Agent-side p95 (s): end_of_turn_delay 2.50, llm_node_ttft 2.72, tts_node_ttfb 3.69, e2e_latency 9.07.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection semantic, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 100.0% (1 of 1 tool errors) |
| Tool errors followed by silence (not judged) | 0 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_mid_order** run 3 (caller_ended): status: expected confirmed, got escalated; missing: 1x masala_chai (regular) with less_sugar; customer: not set
- **hesitation_pause_on_phone** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; customer name: expected 'Ritu', got 'Riru, RITU'
- **hesitation_pause_on_phone** run 3 (caller_ended): status: expected confirmed, got escalated; customer name: expected 'Ritu', got 'Riru'
- **hesitation_undecided_drink** run 2 (caller_ended): status: expected confirmed, got escalated; customer: not set

## Rule violations

None.
