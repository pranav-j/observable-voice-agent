# Eval report: audio mode

Started 2026-10-12T15:24:11+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 66.7% (6/9 runs) |
| Scenarios passing all runs | 1/3 (33.3%) |
| Order exact match | 66.7% (of 9 scored runs) |
| Mean field accuracy | 0.94 |
| Escalation agreement | 66.7% (3 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 9 / 12 |
| Run duration p50 / p95 (s) | 206.1 / 303.8 |
| Agent tokens in / out | 705,088 / 5,429 |
| Caller tokens in / out | 70,391 / 1,519 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 6/9 (66.7%) |
| phone | 2/3 (66.7%) |
| price_question | 1/3 (33.3%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 3/3 | 1.00 | caller_ended x3 |
| hesitation_pause_on_phone | hesitation, phone | 2/3 | 0.94 | caller_ended x3 |
| hesitation_undecided_drink | hesitation, price_question | 1/3 | 0.89 | caller_ended x3 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4601 / 7014 (84 turns) |
| Dead air (over 2 s) | 84 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/9 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 8/9 scripted pauses (88.9%) |
| WER | 13.8% (853 words) |
| WER, clean | 13.8% (853 words) |
| Agent cost per minute | $0.000 ($0.012 over 31.4 min, 9 runs) |
| Replies with a sentence said twice | 2 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.90, llm_node_ttft 1.12, tts_node_ttfb 0.71, e2e_latency 4.70.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 600, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection vad, vad_min_silence_ms 550.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 100.0% (5 of 5 tool errors) |
| Tool errors followed by silence (not judged) | 0 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **hesitation_pause_on_phone** run 2 (caller_ended): status: expected confirmed, got escalated; customer name: expected 'Ritu', got 'Reru'
- **hesitation_undecided_drink** run 1 (caller_ended): status: expected confirmed, got escalated; customer name: expected 'Tanvi', got 'Tnvi'
- **hesitation_undecided_drink** run 3 (caller_ended): status: expected confirmed, got escalated; customer name: expected 'Tanvi', got 'Tnvi'

## Rule violations

None.
