# Eval report: audio mode

Started 2026-10-11T19:05:42+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 25.0% (2/8 runs) |
| Scenarios passing all runs | 1/4 (25.0%) |
| Order exact match | 50.0% (of 8 scored runs) |
| Mean field accuracy | 0.90 |
| Escalation agreement | 75.0% (2 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 3 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 6 / 10 |
| Run duration p50 / p95 (s) | 141.8 / 319.1 |
| Agent tokens in / out | 392,371 / 3,569 |
| Caller tokens in / out | 38,713 / 880 |

## By tag

| Tag | Pass |
|---|---|
| barge_in | 2/8 (25.0%) |
| correction | 0/2 (0.0%) |
| mid_answer | 2/2 (100.0%) |
| readback | 0/4 (0.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| barge_in_mid_answer_switch | barge_in, mid_answer | 2/2 | 1.00 | caller_ended x2 |
| barge_in_readback_add_item | barge_in, readback | 0/2 | 0.79 | time_limit x1, transferred x1 |
| barge_in_readback_remove_item | barge_in, readback | 0/2 | 1.00 | caller_hung_up_early x2 |
| readback_barge_in_size_change | barge_in, correction | 0/2 | 0.80 | caller_ended x1, caller_hung_up_early x1 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 5216 / 9135 (51 turns) |
| Dead air (over 2 s) | 50 turns (98.0%) |
| Barge-in stop p50 / p95 (ms) | 16895 / 18996 (3 barge-ins) |
| False cut-offs | 0/0 scripted pauses (n/a) |
| WER | 15.8% (584 words) |
| WER, SNR 15 dB | 12.2% (98 words) |
| WER, clean | 16.5% (486 words) |
| Agent cost per minute | $0.024 ($0.587 over 24.3 min, 8 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 500, fault no_barge_in, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_model gpt-4o-mini-tts, tts_voice coral.

## Judged

| Metric | Value |
|---|---|
| Error acknowledgement | 87.5% (7 of 8 tool errors) |
| Tool errors followed by silence (not judged) | 1 |
| Judge agreement | not calibrated yet |
| Injection resistance | n/a (0 of 0 runs) |
| Agreed to a discount | 0 runs |
| Total differs from the menu price | 0 runs |

## Failures

- **barge_in_readback_add_item** run 1 (transferred): status: expected confirmed, got escalated; missing: 1x gulab_jamun; customer: not set
- **barge_in_readback_add_item** run 2 (time_limit): status: expected confirmed, got abandoned
- **barge_in_readback_remove_item** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned
- **barge_in_readback_remove_item** run 2 (caller_hung_up_early): status: expected confirmed, got abandoned; extra: 1x chocolate_brownie
- **readback_barge_in_size_change** run 1 (caller_hung_up_early): status: expected confirmed, got abandoned; missing: 1x cold_coffee (medium); extra: 1x cold_coffee (large)
- **readback_barge_in_size_change** run 2 (caller_ended): status: expected confirmed, got escalated; missing: 1x cold_coffee (medium); extra: 1x cold_coffee (large); customer: not set

## Rule violations

None.
