# Eval report: audio mode

Started 2026-10-19T05:30:45+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 100.0% (1/1 runs) |
| Scenarios passing all runs | 1/1 (100.0%) |
| Order exact match | 100.0% (of 1 scored runs) |
| Mean field accuracy | 1.00 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 5 |
| Run duration p50 / p95 (s) | 109.1 / 109.1 |
| Agent tokens in / out | 29,187 / 289 |
| Caller tokens in / out | 3,762 / 54 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 1/1 (100.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_single_coffee | happy_path | 1/1 | 1.00 | caller_ended x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 4743 / 6032 (5 turns) |
| Dead air (over 2 s) | 5 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| Turn ended during a scripted pause, agent's clock | 0/0 scripted pauses (n/a) |
| WER | 11.5% (26 words) |
| WER, clean | 11.5% (26 words) |
| Agent cost per minute | $0.000 ($0.001 over 1.7 min, 1 runs) |
| Replies with a sentence said twice | 0 |
| Agent sent again after not joining | 0 runs |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.86, llm_node_ttft 1.17, tts_node_ttfb 0.55, e2e_latency 5.09.

Agent-side p95 (s): end_of_turn_delay 0.91, llm_node_ttft 1.34, tts_node_ttfb 1.35, e2e_latency 6.32.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, pipeline cascade, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection semantic, vad_min_silence_ms 550.

## Failures

None.

## Rule violations

None.
