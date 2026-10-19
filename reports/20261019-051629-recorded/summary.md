# Eval report: recorded mode

Started 2026-10-19T05:16:29+00:00. Agent gpt-6-luna (prompt v1), caller human (prompt human).

## Overall

| Metric | Value |
|---|---|
| Task success | 50.0% (3/6 runs) |
| Scenarios passing all runs | 3/6 (50.0%) |
| Order exact match | 60.0% (of 5 scored runs) |
| Mean field accuracy | 0.94 |
| Escalation agreement | 83.3% (1 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 9 / 17 |
| Run duration p50 / p95 (s) | 136.6 / 163.0 |
| Agent tokens in / out | 414,689 / 2,911 |
| Caller tokens in / out | 0 / 0 |

## By tag

| Tag | Pass |
|---|---|
| human | 3/6 (50.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| call-20261019-044913-275965 | human | 0/1 | 0.89 | recorded_call x1 |
| call-20261019-045151-742e97 | human | 1/1 | 1.00 | recorded_call x1 |
| call-20261019-045450-a67643 | human | 0/1 | n/a | transferred x1 |
| call-20261019-045707-b836b1 | human | 0/1 | 0.80 | recorded_call x1 |
| call-20261019-045936-008faf | human | 1/1 | 1.00 | recorded_call x1 |
| call-20261019-050203-aa9994 | human | 1/1 | 1.00 | recorded_call x1 |

## Audio

Measured from the worker's two-channel recording, at the agent's end of the line.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 3500 / 6600 (48 turns) |
| Dead air (over 2 s) | 34 turns (70.8%) |
| Barge-in stop p50 / p95 (ms) | 2190 / 13380 (38 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| Turn ended during a scripted pause, agent's clock | not measured |
| WER | n/a (0 words) |
| WER, clean | n/a (0 words) |
| Agent cost per minute | $0.001 ($0.007 over 13.2 min, 6 runs) |
| Replies with a sentence said twice | n/a |
| Agent sent again after not joining | n/a runs |
| Caller hearing | human |

Agent-side p50 (s): not recorded.

Agent-side p95 (s): not recorded.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault none, filler_after_ms 1200, filler_phrases False, llm_model gpt-6-luna, pipeline cascade, preemptive_generation True, stt_model base.en, stt_provider whisper, tts_format mp3, tts_model kokoro-v1.0, tts_provider kokoro, tts_voice af_heart, turn_detection semantic, vad_min_silence_ms 550.

## Failures

- **call-20261019-044913-275965** run 1 (recorded_call): customer name: expected 'Pranav', got 'Pramal'
- **call-20261019-045450-a67643** run 1 (transferred): status: expected confirmed, got escalated
- **call-20261019-045707-b836b1** run 1 (recorded_call): customer name: expected 'Prem', got 'Brem'

## Rule violations

None.
