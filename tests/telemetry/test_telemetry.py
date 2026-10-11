"""Tracing setup and the per-turn log, with an in-memory exporter: no Phoenix needed."""

import json
from pathlib import Path

from livekit.agents.llm import ChatMessage
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_order.telemetry.tracing import PROJECT, setup_tracing
from voice_order.telemetry.turns import TurnLog, turn_record


def test_every_span_carries_the_session_id() -> None:
    exporter = InMemorySpanExporter()
    provider = setup_tracing(
        "http://unused", {"session_id": "call-1", "llm.model": "gpt-6-luna"}, exporter=exporter
    )
    with provider.get_tracer("test").start_as_current_span("user_turn"):
        pass
    provider.force_flush()
    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    assert (span.attributes["session_id"], span.attributes["llm.model"]) == ("call-1", "gpt-6-luna")
    assert span.resource.attributes["openinference.project.name"] == PROJECT


def message(role: str, text: str, **metrics: float) -> ChatMessage:
    return ChatMessage(role=role, content=[text], metrics=metrics)


def test_turn_record_includes_the_metrics() -> None:
    record = turn_record(message("assistant", "Hi!", llm_node_ttft=0.42, tts_node_ttfb=0.31), 3)
    assert record["turn_index"] == 3
    assert (record["role"], record["text"]) == ("assistant", "Hi!")
    assert (record["llm_node_ttft"], record["tts_node_ttfb"]) == (0.42, 0.31)


def test_turn_log_appends_lines_and_counts_caller_turns(tmp_path: Path) -> None:
    log = TurnLog(tmp_path / "call-1" / "turns.jsonl")
    log.add(message("assistant", "Hi, what would you like?"))  # greeting: turn 0
    log.add(message("user", "A dosa", end_of_turn_delay=0.5, transcription_delay=0.2))
    log.add(message("assistant", "One dosa added.", e2e_latency=1.1))
    rows = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert [(r["turn_index"], r["role"]) for r in rows] == [
        (0, "assistant"),
        (1, "user"),
        (1, "assistant"),
    ]
    assert rows[1]["end_of_turn_delay"] == 0.5
    assert rows[2]["e2e_latency"] == 1.1
