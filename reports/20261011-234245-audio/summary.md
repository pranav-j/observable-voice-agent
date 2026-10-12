# Eval report: audio mode

Started 2026-10-11T23:42:45+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 75.0% (6/8 runs) |
| Scenarios passing all runs | 2/4 (50.0%) |
| Order exact match | 87.5% (of 8 scored runs) |
| Mean field accuracy | 0.95 |
| Escalation agreement | 100.0% (0 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 1 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 5 / 8 |
| Run duration p50 / p95 (s) | 209.0 / 330.0 |
| Agent tokens in / out | 504,942 / 3,780 |
| Caller tokens in / out | 38,682 / 932 |

## By tag

| Tag | Pass |
|---|---|
| happy_path | 6/8 (75.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| happy_path_chatty_biryani | happy_path | 2/2 | 1.00 | caller_ended x2 |
| happy_path_details_upfront | happy_path | 1/2 | 0.80 | caller_ended x2 |
| happy_path_multi_item_modifiers | happy_path | 2/2 | 1.00 | caller_ended x2 |
| happy_path_single_coffee | happy_path | 1/2 | 1.00 | caller_ended x1, caller_hung_up_early x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 8487 / 14433 (51 turns) |
| Dead air (over 2 s) | 51 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| WER | 9.0% (543 words) |
| WER, clean | 9.0% (543 words) |
| Agent cost per minute | $0.024 ($0.676 over 28.1 min, 8 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault slow_llm, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_model gpt-4o-mini-tts, tts_voice coral.

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

- **happy_path_details_upfront** run 1 (caller_ended): missing: 1x veg_samosa
- **happy_path_single_coffee** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned

## Rule violations

None.
