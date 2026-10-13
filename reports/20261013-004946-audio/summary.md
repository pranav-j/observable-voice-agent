# Eval report: audio mode

Started 2026-10-13T00:49:46+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 0.0% (0/2 runs) |
| Scenarios passing all runs | 0/1 (0.0%) |
| Order exact match | 100.0% (of 2 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 2 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 4 / 4 |
| Run duration p50 / p95 (s) | 109.9 / 116.0 |
| Agent tokens in / out | 57,994 / 2,124 |
| Caller tokens in / out | 6,104 / 107 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 0/2 (0.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_single_coffee | happy_path | 0/2 | 1.00 | caller_hung_up_early x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 2542 / 4485 (10 turns) |
| Dead air (over 2 s) | 8 turns (80.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| Turn ended during a scripted pause, agent's clock | not measured |
| WER | 7.0% (57 words) |
| WER, clean | 7.0% (57 words) |
| Agent cost per minute | $0.016 ($0.059 over 3.7 min, 2 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): not recorded.

Agent-side p95 (s): not recorded.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-realtime-mini, pipeline realtime, preemptive_generation True, stt_model gpt-realtime-mini, stt_provider realtime, tts_format mp3, tts_model gpt-realtime-mini, tts_provider realtime, tts_voice marin, turn_detection semantic, vad_min_silence_ms 550.

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

- **happy_path_single_coffee** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned
- **happy_path_single_coffee** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

None.
