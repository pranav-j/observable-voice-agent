# Eval report: audio mode

Started 2026-10-12T16:17:38+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 83.3% (5/6 runs) |
| Scenarios passing all runs | 2/3 (66.7%) |
| Order exact match | 83.3% (of 6 scored runs) |
| Mean field accuracy | 0.97 |
| Escalation agreement | 83.3% (1 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 9 / 12 |
| Run duration p50 / p95 (s) | 226.6 / 256.5 |
| Agent tokens in / out | 433,838 / 3,417 |
| Caller tokens in / out | 42,625 / 953 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 5/6 (83.3%) |
| phone | 2/2 (100.0%) |
| price_question | 2/2 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 1/2 | 0.90 | caller_ended x2 |
| hesitation_pause_on_phone | hesitation, phone | 2/2 | 1.00 | caller_ended x2 |
| hesitation_undecided_drink | hesitation, price_question | 2/2 | 1.00 | caller_ended x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 5144 / 7693 (51 turns) |
| Dead air (over 2 s) | 51 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 6/6 scripted pauses (100.0%) |
| WER | 17.5% (519 words) |
| WER, clean | 17.5% (519 words) |
| Agent cost per minute | $0.000 ($0.008 over 19.6 min, 6 runs) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.91, llm_node_ttft 1.24, tts_node_ttfb 0.59, e2e_latency 5.24.

Agent-side p95 (s): end_of_turn_delay 1.27, llm_node_ttft 2.01, tts_node_ttfb 1.42, e2e_latency 7.82.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 150, fault aggressive_eou, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection vad, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 100.0% (2 of 2 tool errors) |
| Tool errors followed by silence (not judged) | 2 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_mid_order** run 2 (caller_ended): status: expected confirmed, got escalated; customer: not set

## Rule violations

None.
