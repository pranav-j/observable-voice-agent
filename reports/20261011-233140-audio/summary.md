# Eval report: audio mode

Started 2026-10-11T23:31:40+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 100.0% (6/6 runs) |
| Scenarios passing all runs | 3/3 (100.0%) |
| Order exact match | 100.0% (of 6 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 7 / 9 |
| Run duration p50 / p95 (s) | 194.7 / 266.0 |
| Agent tokens in / out | 356,325 / 2,661 |
| Caller tokens in / out | 36,416 / 749 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 6/6 (100.0%) |
| phone | 2/2 (100.0%) |
| price_question | 2/2 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 2/2 | 1.00 | caller_ended x2 |
| hesitation_pause_on_phone | hesitation, phone | 2/2 | 1.00 | caller_ended x2 |
| hesitation_undecided_drink | hesitation, price_question | 2/2 | 1.00 | caller_ended x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 5717 / 8347 (44 turns) |
| Dead air (over 2 s) | 44 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| WER | 19.8% (394 words) |
| WER, clean | 19.8% (394 words) |
| Agent cost per minute | $0.024 ($0.496 over 21.0 min, 6 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 150, fault aggressive_eou, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_model gpt-4o-mini-tts, tts_voice coral.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | n/a (0 of 0 tool errors) |
| Tool errors followed by silence (not judged) | 2 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

None.

## Rule violations

None.
