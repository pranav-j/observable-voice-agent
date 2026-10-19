"""The calls dashboard, from recordings on disk: no network, no Phoenix."""

import json
from pathlib import Path
from typing import Any

from voice_order.telemetry.dashboard import (
    by_day,
    load_calls,
    main,
    outcome,
    phoenix_traces,
    render,
)

DAY_ONE = 1_792_300_000.0  # a fixed moment; the second day is 24 h later


def record(
    root: Path,
    session_id: str,
    *,
    started: float = DAY_ONE,
    replies: tuple[float, ...] = (4.0, 6.0),
    tools: tuple[tuple[str, bool], ...] = (("confirm_order", True),),
    cost: float = 0.002,
    seconds: float = 120.0,
    config: dict[str, Any] | None = None,
) -> None:
    folder = root / session_id
    folder.mkdir(parents=True)
    turns = [{"role": "user", "created_at": started, "text": "Priya, 98765 23456"}]
    turns += [
        {"role": "assistant", "created_at": started + i + 1, "e2e_latency": r}
        for i, r in enumerate(replies)
    ]
    (folder / "turns.jsonl").write_text("\n".join(json.dumps(t) for t in turns))
    (folder / "tool_calls.jsonl").write_text(
        "\n".join(json.dumps({"name": n, "result": {"ok": ok}}) for n, ok in tools)
    )
    usage = {"total_cost_usd": cost, "duration_seconds": seconds}
    (folder / "usage.json").write_text(json.dumps(usage))
    (folder / "config.json").write_text(
        json.dumps(config or {"stt_provider": "whisper", "tts_provider": "kokoro"})
    )


def test_outcome_comes_from_the_tool_calls() -> None:
    assert outcome([{"name": "confirm_order", "result": {"ok": True}}]) == "placed"
    assert outcome([{"name": "transfer_to_human", "result": {"ok": True}}]) == "handed to a person"
    assert outcome([{"name": "confirm_order", "result": {"ok": False}}]) == "not placed"


def test_calls_are_read_and_grouped_by_day(tmp_path: Path) -> None:
    record(tmp_path, "call-1", replies=(2.0, 4.0))
    record(tmp_path, "audio-scenario-r1", started=DAY_ONE + 60, tools=(("confirm_order", False),))
    record(tmp_path, "call-2", started=DAY_ONE + 86_400, tools=(("transfer_to_human", True),))
    (tmp_path / "call-never-saved").mkdir()  # the worker didn't get to write anything
    calls = load_calls(tmp_path)
    assert [c.session_id for c in calls] == ["call-1", "audio-scenario-r1", "call-2"]
    assert [c.kind for c in calls] == ["real", "simulated", "real"]
    assert calls[1].tool_errors == 1
    days = by_day(calls)
    assert [d.calls for d in days] == [2, 1]
    assert days[0].outcomes == {"placed": 1, "handed to a person": 0, "not placed": 1}
    assert days[0].p50 == 4.0  # replies 2, 4, 4, 6: the nearest-rank median
    assert days[0].cost_per_minute == 0.001  # 0.004 over 4 minutes


def test_fault_runs_are_marked(tmp_path: Path) -> None:
    config = {"stt_provider": "whisper", "tts_provider": "kokoro", "fault": "slow_llm"}
    record(tmp_path, "audio-x-r1", config=config)
    assert load_calls(tmp_path)[0].speech == "whisper/kokoro, fault slow_llm"


def test_the_page_has_numbers_but_no_conversation(tmp_path: Path) -> None:
    record(tmp_path, "call-1")
    html = render(load_calls(tmp_path), {"call-1": "abc123"}, "http://phoenix", "recordings")
    assert "Real calls, from the web page" in html
    assert 'href="http://phoenix/projects/voice-order-agent/traces/abc123"' in html
    assert "Priya" not in html
    assert "98765" not in html


def test_phoenix_down_means_no_links_not_a_crash() -> None:
    assert phoenix_traces("http://127.0.0.1:9", timeout=0.5) == {}


def test_cli_writes_the_page(tmp_path: Path) -> None:
    record(tmp_path / "recordings", "call-1")
    out = tmp_path / "dash" / "index.html"
    assert (
        main(["--recordings", str(tmp_path / "recordings"), "--out", str(out), "--phoenix", ""])
        == 0
    )
    assert "Voice agent calls" in out.read_text()
