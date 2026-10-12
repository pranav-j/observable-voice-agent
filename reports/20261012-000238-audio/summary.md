# Eval report: audio mode

Started 2026-10-12T00:02:38+00:00. Agent gpt-6-luna (prompt v1), caller gpt-6-luna (prompt v4). 2 calls at a time.

## Overall

| Metric | Value |
|---|---|
| Task success | 33.3% (2/6 runs) |
| Scenarios passing all runs | 1/3 (33.3%) |
| Order exact match | 33.3% (of 6 scored runs) |
| Mean field accuracy | 0.83 |
| Escalation agreement | 83.3% (1 escalated, 0 expected) |
| Errors | 0 |
| Caller hung up mid-order | 0 runs |
| Tool-round limit hits | 0 |
| Confirmed before the caller replied | 0 runs |
| Turns p50 / p95 | 7 / 7 |
| Run duration p50 / p95 (s) | 178.0 / 204.5 |
| Agent tokens in / out | 328,447 / 2,800 |
| Caller tokens in / out | 30,633 / 677 |

## By tag

| Tag | Pass |
|---|---|
| hesitation | 2/6 (33.3%) |
| phone | 2/2 (100.0%) |
| price_question | 0/2 (0.0%) |

## By scenario

| Scenario | Tags | Pass | Field accuracy | End reasons |
|---|---|---|---|---|
| hesitation_pause_mid_order | hesitation | 0/2 | 0.65 | caller_ended x1, transferred x1 |
| hesitation_pause_on_phone | hesitation, phone | 2/2 | 1.00 | caller_ended x2 |
| hesitation_undecided_drink | hesitation, price_question | 0/2 | 0.83 | caller_ended x2 |

## Audio

Measured from the caller's side, from the audio it received.

| Metric | Value |
|---|---|
| Response latency p50 / p95 (ms) | 6249 / 9950 (38 turns) |
| Dead air (over 2 s) | 38 turns (100.0%) |
| Barge-in stop p50 / p95 (ms) | n/a / n/a (0 barge-ins) |
| False cut-offs | 0/6 scripted pauses (0.0%) |
| Turn ended during a scripted pause, agent's clock | 4/6 scripted pauses (66.7%) |
| WER | 19.5% (369 words) |
| WER, clean | 19.5% (369 words) |
| Agent cost per minute | $0.024 ($0.411 over 17.1 min, 6 runs; includes estimates) |
| Replies with a sentence said twice | 0 |
| Caller hearing | transcript |

Agent-side p50 (s): end_of_turn_delay 0.58, llm_node_ttft 1.26, tts_node_ttfb 1.09, e2e_latency 3.96.

Detector: frame_ms 10, min_silence_ms 300, min_speech_ms 30, sample_rate 16000, threshold_dbfs -45.0.

Agent config: agent_prompt_version v1, eou_silence_ms 150, fault aggressive_eou, filler_phrases False, llm_model gpt-6-luna, preemptive_generation False, stt_model gpt-live-transcribe, tts_model gpt-4o-mini-tts, tts_voice coral.

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

- **hesitation_pause_mid_order** run 1 (caller_ended): missing: 1x mysore_masala_dosa with extra_butter; extra: 1x mysore_masala_dosa
- **hesitation_pause_mid_order** run 2 (transferred): status: expected confirmed, got escalated; missing: 1x mysore_masala_dosa with extra_butter; extra: 1x masala_dosa with extra_butter; customer: not set
- **hesitation_undecided_drink** run 1 (caller_ended): customer name: expected 'Tanvi', got 'Tan V'
- **hesitation_undecided_drink** run 2 (caller_ended): customer name: expected 'Tanvi', got 'Tan V'

## Rule violations

None.
