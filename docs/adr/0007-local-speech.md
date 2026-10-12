# 0007: Local speech models, switchable with hosted ones

- **Status:** accepted
- **Date:** 2026-10-12

## Context

Every audio eval call paid for speech three times: recognition of the caller, the agent's voice, and the simulated caller's voice. In the first full audio run (`reports/20261011-163931-audio`), recognition was about 62% of the cost and the agent's voice about 25%. The simulated caller's voice was about 12%, and all the LLM calls together were about 1%. At around eight cents a call, a full suite cost several dollars. Each fix that needed a re-run cost that again, and the credit kept running out partway through.

Speech models that run well on a laptop now exist. The development machine is an Apple M4 with 24 GB of memory.

## Decision

- **Recognition:** `faster-whisper` running a Whisper model locally on the CPU (int8), selected with `STT_PROVIDER=whisper` and `WHISPER_MODEL`. It plugs into LiveKit as a non-streaming recognizer, so LiveKit runs it on each utterance its voice detection finds.
- **The agent's voice:** Kokoro (`kokoro-onnx`), selected with `TTS_PROVIDER=kokoro` and `KOKORO_VOICE`, synthesizing a sentence at a time.
- **The simulated caller's voice:** Kokoro as well, chosen with the eval runner's `--caller-voice kokoro`.
- **The LLM stays hosted.** It's about 1% of the cost, and the agent depends on reliable tool calling, which small local models are noticeably worse at.
- **Local speech is the default.** With a realistic simulated caller, it matched hosted speech on task success, 85 of 93 in both `reports/20261011-163931-audio` and `reports/20261012-072648-audio`. Replies started 28% sooner at p50, and the agent's speech cost nothing. The agent code had also improved between those two runs, so this isn't a pure comparison of the two pipelines.
- **The simulated caller keeps OpenAI's voice by default.** Kokoro mispronounces Indian names. With a Kokoro caller, the local pipeline passed only 64 of 93 (`reports/20261012-050510-audio`), mostly on names, and offline the same recognizer got twice as many names right when an OpenAI voice said them. Caller speech is about a cent per call.
- **Both pipelines stay available.** The hosted models remain the other setting, not deleted code. Every call saves which providers it used, so reports from the two can't be mixed up.
- Model inference runs in a worker thread, so a call's event loop never waits on it. The models load once per worker process, in prewarm.
- The model files live in a gitignored `models/` folder. `make models` downloads them.

`faster-whisper` was chosen over `mlx-whisper`: it installs on Linux CI as well as macOS, and it doesn't pull in PyTorch.

## Alternatives

- **Stay hosted and buy more credit.** That works, but every re-run costs real money, which discourages exactly the repeated measurement the eval harness exists for.
- **Local everything, including the LLM.** It saves the last 1% at a real cost to tool-calling reliability.
- **`mlx-whisper`.** It's faster on Apple Silicon, but Mac-only and much heavier to install.

## Consequences

- Reports from the local pipeline aren't comparable with the hosted baseline: the recognizer and both voices are different. The local pipeline gets its own baseline, and the hosted reports stay as they are.
- Kokoro's English voices are American or British; Hindi voices exist, but they speak English with their own accent. The simulated callers sound less like the Indian-English personas they're meant to be, which may make recognition easier than it would be with real callers.
- With two calls at once, both agents' speech models and the harness share one machine's CPU, so local compute is now part of the measured latency. Reports record the concurrency, and comparisons keep it fixed.
- Comparing hosted and local recognition on the same scenarios is the planned speech-to-text experiment, and running it now costs almost nothing.
