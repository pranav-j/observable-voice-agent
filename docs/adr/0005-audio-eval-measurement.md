# 0005: How the audio evals hear the agent and measure timing

- **Status:** accepted
- **Date:** 2026-10-11

## Context

In audio mode, a simulated caller joins the LiveKit room as a real participant. It speaks into a microphone track and listens to the agent's audio, just as a person would. The timing metrics (response latency, dead air, how fast the agent stops when interrupted, false cut-offs during the caller's pauses) have to be measured **from the caller's side, from audio**, not from timestamps the agent reports about itself. Otherwise the harness would only confirm what the agent already believes.

That leaves two decisions:

1. **How the caller understands what the agent said,** so its LLM can reply.
2. **How speech onset and offset are found** in the audio the caller receives. Every timing metric depends on this, so it must be the same in every run being compared.

## Decision

### Hearing mode: `--hearing`, default `transcript`

- `transcript` (the default): the caller reads the agent's words from LiveKit's transcription stream, the same text the web UI shows. It costs nothing extra and adds no delay.
- `stt`: the caller transcribes the agent's received audio itself with `gpt-4o-mini-transcribe`, once each agent utterance ends. This is more faithful, because the caller then hears only what actually came out of the speaker, and an interrupted sentence stays cut off. It costs more and is slower.

The default is `transcript` to keep runs cheap. Timing doesn't depend on hearing mode, because timing always comes from the audio.

### The caller's own speech: known, not detected

The caller generates its own audio (text-to-speech, plus noise mixed in at the scenario's signal-to-noise ratio), so it knows exactly where each utterance and each scripted pause starts and ends. Those boundaries are logged on a monotonic clock as the frames are sent, with a small audio-source buffer so the send time stays close to when the audio actually goes out.

### The agent's speech: a fixed energy detector

The agent's received audio is logged on the same clock as it arrives, and saved. Onset and offset come from a deterministic energy detector run over that audio after the call:

- 16 kHz mono, 10 ms frames, RMS level in dBFS
- a frame counts as speech above **-45 dBFS**
- **onset**: the first frame of a run of at least **30 ms** of speech
- **offset**: the last speech frame before at least **300 ms** of non-speech

For barge-in timing, the agent "stops" at the end of its reply, not the end of its current sentence: speech segments less than 1.5 seconds apart count as one reply. After a real stop, the agent's next reply can't begin that soon, because it needs an end of turn and an LLM call first. The first version measured to the end of the current segment. Seeded-fault validation showed that missed an agent that ignores the caller: it pauses at a sentence break and carries on. The rule changed on 2026-10-12, and every compared report was re-scored from its saved audio with `python -m evals.rescore`.

These thresholds live in one place in the code, and every report records them. They must not change between runs that are compared. If they ever have to change, all compared runs get re-scored from their saved audio.

The detector only ever runs on the agent's track. That audio is synthesized speech passed through the Opus codec, with no noise mixed in, so a level threshold separates speech from silence reliably. Noise is only added to what the caller sends.

## Alternatives

- **Silero VAD,** the model the agent itself uses. It's more robust on noisy audio, but in LiveKit's packaging it only runs inside a live event loop. It's also a learned model whose output can shift between versions. For clean agent audio, a transparent level threshold is easier to trust and to re-run offline.
- **Agent-reported timestamps** from LiveKit's metrics or spans. These are useful for explaining *where* time went, and they stay in the traces, but they measure the agent from the inside, not what a caller hears.
- **Caller-side STT as the default.** It's more realistic, but it adds cost and a delay to every turn, and it doesn't change any timing metric.

## Consequences

- One-way network delay is included in the measured response latency, which is what a real caller experiences too. In local runs it's small.
- Timing resolution is bounded by the 10 ms frame size and the audio buffering on the send side. That's fine for metrics reported in hundreds of milliseconds.
- Every audio run keeps the agent's received audio and the event timeline, so metrics can be recomputed if the detector ever changes.
- In `transcript` mode, the caller "hears" a whole sentence even if the agent was cut off mid-way. Scenarios where that matters, like interruptions, can be run with `--hearing stt`.
