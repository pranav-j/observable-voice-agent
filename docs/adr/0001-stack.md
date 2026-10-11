# 0001: Stack and toolchain

- **Status:** accepted
- **Date:** 2026-10-11

## Context

The project is a real-time voice agent that takes pickup food orders, plus an eval harness that calls the agent with simulated callers over real audio and scores each call. The stack has to support:

- Low-latency, two-way audio with barge-in, from both a browser and a scripted caller bot.
- Order state that lives in code and can be changed only through typed tools. The voice pipeline and a text-only test loop have to share that same core.
- Timing metrics measured from the audio the caller actually receives, which means the caller bot must be a real participant in the same media session.
- Per-turn tracing (speech end, STT final, first LLM token, tool calls, first TTS byte) that can be inspected and compared across runs.
- A final order state that the harness can read after each call.
- A reproducible local setup, and CI that runs the same checks as a developer machine.

## Decision

**Real-time transport: LiveKit**, with the agent built on **LiveKit Agents (Python)**. Local development uses the official `livekit-server` Docker image in dev mode. The browser joins with the LiveKit JS SDK, and the eval caller bot joins the same room as an ordinary participant, so its audio takes the same WebRTC path as a human's.

**Framework-independent core.** Menu, order state machine, tools and prompts are plain Python modules under `src/voice_order/` with no LiveKit imports. The voice worker (`agent/`) and the text-mode loop (`textmode/`) both wire up this core. A unit test parses the core's imports and fails if it ever imports `livekit` or the worker.

**Backend: FastAPI** for token issuing, menu and order endpoints. **Database: Postgres**, storing orders keyed by session so the harness can read final state.

**Frontend: React + TypeScript (strict) + Vite + Zustand.** Zustand holds the call state that LiveKit events update: transcript, order panel and latency numbers.

**Tracing: OpenTelemetry, exported to Arize Phoenix.** Instrumentation stays vendor-neutral OTel. Phoenix runs locally in Docker and has views built for LLM and tool-call spans.

**Local infrastructure: Docker Compose** runs Postgres, LiveKit and Phoenix with healthchecks, and `make up` waits until all three are healthy. Two LiveKit settings exist because Docker Desktop runs containers inside a VM: the server advertises `127.0.0.1` as its media address, and WebRTC uses one muxed UDP port (7882) instead of a large port range.

**Python toolchain:**

- The interpreter comes from **pyenv**, pinned in `.python-version`.
- The project environment is `.venv`, created with the stdlib `venv` module from that interpreter.
- **uv** manages dependencies inside `.venv` from a committed `uv.lock`. uv is configured never to download or choose its own Python (`python-downloads = "never"`, `python-preference = "only-system"`).
- Pydantic v2 for models, ruff for lint and format, mypy in strict mode, pytest for tests.

**Node toolchain:** **nvm**, with the version pinned in `.nvmrc` (Node 24 LTS). `engines` plus `engine-strict` in `web/` refuse other versions. npm with a committed `package-lock.json`, and Oxlint for linting.

**Checks:** a `Makefile` is the single entry point for setup, services, lint and tests. pre-commit runs hygiene checks plus ruff and mypy from `.venv`. GitHub Actions runs the same `make` targets, with every action pinned to a commit SHA.

## Alternatives

- **Pipecat (with Daily or another transport)** instead of LiveKit Agents. It is a capable cascade framework, but LiveKit gives one system for the SFU, client SDKs, agent framework and room participants. That makes it straightforward to run the caller bot as a real participant and measure from received audio. Self-hosting the server also avoids depending on a vendor for local work.
- **Raw WebRTC (aiortc) or telephony media streams (e.g. Twilio).** These offer more control, or a phone-first setup, but mean rebuilding turn handling, reconnection and client SDKs. Telephony can be added later through LiveKit SIP.
- **A provider's speech-to-speech API used directly** (e.g. a realtime WebRTC endpoint). This hides the cascade stages, so per-stage latency and tool-call behavior can't be observed or swapped. Speech-to-speech will be evaluated as a comparison inside the LiveKit setup instead.
- **SQLite** instead of Postgres. It would be simpler, but the agent worker, backend and harness are separate processes that all read and write orders, and the demo deployment will want a real server database.
- **Jaeger or Grafana Tempo, Langfuse, LangSmith** for tracing. Jaeger and Tempo handle OTel well but have no LLM-aware views. Langfuse and LangSmith are LLM-focused, but either self-hosting them is heavier or they are hosted services. Phoenix accepts plain OTLP and runs as one container.
- **Next.js, or Redux,** for the frontend. A single-page operator dashboard needs no server rendering, and Zustand covers the state needs with less code.
- **Poetry, Conda, or uv-managed Python downloads.** uv is faster and its lockfile works across platforms. Interpreters stay with pyenv so that every project on the machine gets Python the same way.
- **pnpm** instead of npm. It's faster, but npm ships with Node and the web app has few dependencies.

## Consequences

- Local development needs Docker, pyenv and nvm. `make setup` checks the Python version and fails with an install hint if it doesn't match, and npm refuses a Node version outside `engines`.
- LiveKit's networking config is tuned for Docker Desktop on a single machine. A deployment needs a different `node_ip` and port setup, which will be covered in its own ADR.
- Keeping the core free of LiveKit makes the text-mode tests and evals cheap and deterministic. The cost is a thin adapter layer in the voice worker.
- STT, LLM and TTS providers are not chosen here. They sit behind environment-variable config and get their own ADR.
- Pinned versions (lockfiles, Docker image tags, action SHAs) make runs reproducible but need deliberate updates.
