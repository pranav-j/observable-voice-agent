"""Per-session provider usage, and its estimated cost from config/rates.yaml.

LiveKit reports usage per model: LLM tokens, STT audio seconds, TTS characters and
tokens. Cost is usage times the configured rates. A model with no rate is listed as
unpriced rather than silently counted as free.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

RATES_PATH = Path(__file__).resolve().parents[3] / "config" / "rates.yaml"
# LiveKit reports some providers by API host; rates are keyed by provider name.
PROVIDER_ALIASES = {"api.openai.com": "openai"}


class LLMRate(BaseModel):
    input_per_1m: float
    cached_input_per_1m: float = 0.0
    output_per_1m: float


class STTRate(BaseModel):
    per_minute: float


class TTSRate(BaseModel):
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    per_1m_characters: float = 0.0


class Rates(BaseModel):
    llm: dict[str, LLMRate] = Field(default_factory=dict)
    stt: dict[str, STTRate] = Field(default_factory=dict)
    tts: dict[str, TTSRate] = Field(default_factory=dict)


def load_rates(path: Path = RATES_PATH) -> Rates:
    return Rates.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _get(usage: Any, name: str) -> float:
    return float(getattr(usage, name, 0) or 0)


def summarize_usage(
    model_usage: list[Any], rates: Rates, call_seconds: float | None = None
) -> dict[str, Any]:
    """Usage per model plus estimated cost. `model_usage` is LiveKit's per-model usage list.

    Streaming STT bills for all the audio sent, but some providers report no duration.
    Then the call's length stands in for it, and the line is marked as estimated.
    """
    lines = []
    total = 0.0
    unpriced = []
    for u in model_usage:
        kind = getattr(u, "type", "").replace("_usage", "")
        provider = getattr(u, "provider", "")
        key = f"{PROVIDER_ALIASES.get(provider, provider)}/{getattr(u, 'model', '')}"
        line: dict[str, Any] = {"kind": kind, "model": key}
        cost: float | None = None
        if kind == "llm":
            cached = _get(u, "input_cached_tokens")
            line |= {
                "input_tokens": int(_get(u, "input_tokens")),
                "cached_input_tokens": int(cached),
                "output_tokens": int(_get(u, "output_tokens")),
            }
            if (r := rates.llm.get(key)) is not None:
                fresh = _get(u, "input_tokens") - cached
                cost = (
                    fresh * r.input_per_1m
                    + cached * r.cached_input_per_1m
                    + _get(u, "output_tokens") * r.output_per_1m
                ) / 1e6
        elif kind == "stt":
            seconds = _get(u, "audio_duration")
            if seconds == 0 and call_seconds:
                seconds = call_seconds
                line["estimated_from_call_length"] = True
            line["audio_seconds"] = round(seconds, 2)
            if (s := rates.stt.get(key)) is not None:
                cost = seconds / 60 * s.per_minute
        elif kind == "tts":
            line |= {
                "characters": int(_get(u, "characters_count")),
                "input_tokens": int(_get(u, "input_tokens")),
                "output_tokens": int(_get(u, "output_tokens")),
                "audio_seconds": round(_get(u, "audio_duration"), 2),
            }
            if (t := rates.tts.get(key)) is not None:
                cost = (
                    _get(u, "input_tokens") * t.input_per_1m
                    + _get(u, "output_tokens") * t.output_per_1m
                    + _get(u, "characters_count") * t.per_1m_characters
                ) / 1e6
        if cost is None:
            unpriced.append(key)
        else:
            line["cost_usd"] = round(cost, 6)
            total += cost
        lines.append(line)
    return {"models": lines, "total_cost_usd": round(total, 6), "unpriced": unpriced}
