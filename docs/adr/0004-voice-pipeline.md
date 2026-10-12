# 0004: Voice pipeline providers and turn handling

- **Status:** accepted
- **Date:** 2026-10-11

## Context

The voice agent is a cascade. Voice activity detection and turn detection decide when the caller has finished. Then speech-to-text transcribes it, the LLM decides what to do (calling the same tools as text mode), and text-to-speech speaks the reply. Barge-in has to work, so the agent stops talking when the caller starts. Latency matters at every stage.

Constraints:

- **Self-hosted LiveKit server** in dev mode. LiveKit Agents 1.8.x defaults some features to LiveKit's cloud gateway in dev mode, notably a cloud turn-detector model and an "adaptive" interruption model. Those don't work against a self-hosted server without LiveKit Cloud credentials.
- **No new paid vendor without a reason.** An OpenAI key already exists (ADR 0003).
- **Same core as text mode.** The worker must call the same tool `dispatch`, prompts and state machine, so the two modes can't drift apart.
- **Timing comes from audio** that's actually heard. The pipeline still needs per-turn traces to explain where the time went.

## Decision

- **Framework:** LiveKit Agents (Python), pinned to exactly 1.8.6 along with its plugins. These APIs change often, and that version's source was read to write this ADR.
- **Speech-to-text:** OpenAI `gpt-live-transcribe` over its realtime streaming connection, chosen for low latency. `STT_MODEL` selects another model. Non-streaming ones like `gpt-4o-mini-transcribe` work too, with VAD-based chunking.
- **LLM:** OpenAI Responses API through `livekit-plugins-openai`, with the same model and `reasoning: none` as text mode (`LLM_MODEL`).
- **Text-to-speech:** OpenAI `gpt-4o-mini-tts`, with the voice set by `TTS_VOICE`. It's non-streaming per request, so LiveKit splits the reply into sentences and starts speaking after the first complete one.
- **Voice activity detection:** Silero, which runs locally and is bundled with the plugin.
- **Turn detection:** LiveKit's local turn-detector model (`inference.TurnDetector(version="v1-mini")`), never the cloud one. The minimum silence before a turn can end comes from `EOU_SILENCE_MS`.
- **Barge-in:** enabled, with VAD-based interruption (`interruption.mode = "vad"`), because the adaptive mode needs the cloud.
- **Preemptive generation:** set by `ENABLE_PREEMPTIVE_GENERATION`, on by default. It was off for a while: I'd blamed it for the agent saying a sentence twice, but the first full audio run (`reports/20261011-163931-audio`) showed doubling with it off too, after caller turns that arrived in two pieces. Measured on local speech, it cut caller-side latency from 5106 to 4761 ms at p50 and from 8483 to 7157 ms at p95 (`reports/20261012-093814-audio` against `reports/20261012-102638-audio`). One reply in 18 calls was doubled, about the rate seen with it off.
- **Tools:** each core tool is registered as a LiveKit raw-schema function tool. Its schema is the same one generated for text mode, and calling it runs the same `dispatch`. Results go back to the model as JSON strings. LiveKit would otherwise `str()` a dict into a Python repr.
- **Recording:** LiveKit's built-in session recorder, which writes one stereo file with the caller on the left channel and the agent on the right, on one timeline. It lands in a temporary directory that's deleted when the job ends, so the worker copies it into `recordings/<session_id>/` in the session-end hook and splits it into `caller.wav` and `agent.wav`.
- **Tracing:** LiveKit's built-in OpenTelemetry spans (`user_turn`, `eou_detection`, `agent_turn`, `llm_node`, `tts_node`, `function_tool`, and others), exported to Phoenix over OTLP/HTTP, with our session id added. Per-turn timings from each message's metrics (transcription delay, end-of-turn delay, LLM time to first token, TTS time to first byte, end-to-end latency) are also appended to `recordings/<session_id>/turns.jsonl`.

## Alternatives

- **Deepgram for speech-to-text, Cartesia or ElevenLabs for text-to-speech.** These are known for low latency and true streaming, which would cut time to first audio. They mean new accounts and keys, so they're candidates for the latency and STT experiments, not the default.
- **Local faster-whisper and Kokoro or Piper.** Free and private, but slower on a laptop CPU than a hosted API. faster-whisper is still useful as a free comparison in the STT experiment.
- **LiveKit Inference (the cloud gateway).** One key for STT, LLM and TTS, plus the better cloud turn detector and adaptive interruption. But it ties local development to LiveKit Cloud, which goes against the self-hosted setup in ADR 0001.
- **A speech-to-speech model as the default.** That hides the stages and makes per-stage timing and tool behavior harder to see. It gets compared against the cascade in its own experiment instead.

## Consequences

- Everything spoken or heard goes through one vendor. An OpenAI outage stops the voice agent.
- TTS waits for a whole first sentence, which adds latency compared with a streaming TTS. This is one of the first things to measure.
- The local `v1-mini` turn detector is smaller than LiveKit's cloud model. The turn-detection experiment compares silence thresholds and detectors.
- Recordings, traces and turn timings all come from the same session, so a slow turn in Phoenix can be listened to in the recording.
- Upgrading LiveKit means re-checking the APIs used here. The exact pin makes that a deliberate step.
