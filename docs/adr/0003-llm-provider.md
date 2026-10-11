# 0003: LLM provider and models

- **Status:** accepted
- **Date:** 2026-10-11

## Context

Three parts of the system need an LLM:

1. **The agent**, in both voice and text mode. In a voice cascade the LLM sits between end of speech and the first audio the caller hears, so its time to first token adds directly to response latency. It also has to call tools reliably. Order state, prices and the read-back all live in code (see ADR 0001), so the model mainly has to follow the conversation flow and pick the right tool with the right ids, not reason deeply.
2. **The simulated caller** in the eval harness. It plays a persona from a scenario file. Its cost is tracked separately from the agent's.
3. **Later experiments**, which compare a speech-to-speech model against the cascade.

Providers should stay swappable through configuration, and every new vendor means another account, key and bill to manage.

## Decision

- **Provider: OpenAI.** An account and key already exist. LiveKit Agents has a maintained OpenAI plugin, and the same provider offers realtime speech-to-speech models for the later comparison.
- **Agent model: `gpt-6-luna` with reasoning effort `none`.** It is OpenAI's lowest-cost current model, and the only one listed where reasoning can be turned off completely, which keeps time to first token low. At the time of writing, OpenAI's pricing page lists it at $0.10 input and $0.50 output per million tokens.
- **Caller model: `gpt-6-luna` as well,** to keep eval runs cheap.
- **Configuration:** `LLM_MODEL` and `CALLER_LLM_MODEL` select the models, and `OPENAI_API_KEY` lives only in `.env`. Changing models needs no code change.
- **Clients:** text mode uses the official `openai` Python SDK, and the voice worker uses `livekit-plugins-openai`. Both are fed the same tool schemas generated from the core.

Before this was accepted, a single request confirmed that the key can use `gpt-6-luna`, that the API accepts reasoning effort `none` together with function tools, and that the model called `search_menu` with sensible arguments given only the generated schema. That was a smoke test, not a measurement. Latency and accuracy numbers will come from eval runs saved in `reports/`.

## Alternatives

- **`gpt-6.1-sol`.** It is smarter, but about 20 times the price per token and expected to be slower. It's kept as a comparison point: if Luna's task success is too low, the evals will show it, and switching is a configuration change.
- **`gpt-5.4-mini`.** The previous generation's small model. It costs more than Luna and has no reason to be preferred.
- **Anthropic (Claude Haiku), Google (Gemini Flash).** Both are capable tool-calling models with LiveKit plugins, but each adds a vendor and a key. They remain options if OpenAI falls short.
- **Groq or Cerebras with open-weight models.** These are known for very low time to first token, but tool-calling reliability varies by model, and they add a vendor. They're worth trying in the latency experiments.

## Consequences

- One vendor for the LLM, and probably for the speech-to-speech comparison too, so an OpenAI outage stops the agent. That's acceptable for a demo.
- The agent and the simulated caller run on the same model, which could make conversations easier than they would be with real people. Personas, scripted behaviors and the human-call recordings are there to counter that, and `CALLER_LLM_MODEL` can be changed independently.
- Tests that call the API are marked `integration` and skip when `OPENAI_API_KEY` is empty, as it is in CI by default.
- Per-token prices change. Cost-per-minute figures will be computed from usage records and a rates file, not hard-coded.
