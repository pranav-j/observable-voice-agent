"""Finding the tool errors worth judging, in text transcripts and voice recordings."""

import json
from pathlib import Path
from typing import Any

from evals.judge.cases import cases_from_recording, cases_from_transcript
from evals.text_run import TranscriptEntry


def agent(text: str, *calls: dict[str, Any]) -> TranscriptEntry:
    return TranscriptEntry(speaker="agent", text=text, tool_calls=list(calls))


def failed(name: str, error: str, **arguments: Any) -> dict[str, Any]:
    return {"name": name, "arguments": arguments, "ok": False, "error": error}


def worked(name: str, **arguments: Any) -> dict[str, Any]:
    return {"name": name, "arguments": arguments, "ok": True}


def test_text_cases_pair_an_error_with_the_turn_text() -> None:
    transcript = [
        TranscriptEntry(speaker="caller", text="A pizza please"),
        agent("Sorry, we don't have pizza.", failed("add_item", "UNKNOWN_ITEM", item_id="pizza")),
    ]
    (case,) = cases_from_transcript("s1", transcript)
    assert (case.tool, case.error, case.reply) == (
        "add_item",
        "UNKNOWN_ITEM",
        "Sorry, we don't have pizza.",
    )
    assert case.case_id == "s1#0"


def test_internal_errors_and_fixed_retries_are_not_cases() -> None:
    transcript = [
        agent("Is that right?", failed("confirm_order", "WAITING_FOR_CALLER")),
        agent(
            "Added.",
            failed("add_item", "INVALID_SIZE", item_id="latte", size_id="big"),
            worked("add_item", item_id="latte", size_id="large"),
        ),
    ]
    assert cases_from_transcript("s1", transcript) == []


def _recording(tmp_path: Path, calls: list[dict[str, Any]], rows: list[dict[str, Any]]) -> Path:
    folder = tmp_path / "audio-x-r1"
    folder.mkdir()
    (folder / "tool_calls.jsonl").write_text("\n".join(json.dumps(c) for c in calls))
    (folder / "transcript.json").write_text(json.dumps(rows))
    return folder


def test_voice_reply_is_everything_said_before_the_caller_speaks_again(tmp_path: Path) -> None:
    error = {"ok": False, "error": "OUT_OF_STOCK", "message": "Mango lassi is out."}
    folder = _recording(
        tmp_path,
        [
            {
                "name": "add_item",
                "arguments": {"item_id": "mango_lassi"},
                "result": error,
                "created_at": 10.0,
            }
        ],
        [
            {"role": "user", "text": "A mango lassi", "created_at": 9.0},
            # said in the same step as the call, so logged just after it
            {"role": "assistant", "text": "Let me check.", "created_at": 10.5},
            {"role": "assistant", "text": "Sorry, it's sold out today.", "created_at": 12.0},
            {"role": "user", "text": "Okay, a sweet lassi then", "created_at": 15.0},
            {"role": "assistant", "text": "Added.", "created_at": 17.0},
        ],
    )
    (case,) = cases_from_recording(folder)
    assert case.reply == "Let me check. Sorry, it's sold out today."
    assert case.message == "Mango lassi is out."


def test_voice_retry_before_the_next_caller_turn_is_not_a_case(tmp_path: Path) -> None:
    folder = _recording(
        tmp_path,
        [
            {
                "name": "set_customer",
                "arguments": {},
                "result": {"ok": False, "error": "INVALID_PHONE"},
                "created_at": 10.0,
            },
            {"name": "set_customer", "arguments": {}, "result": {"ok": True}, "created_at": 11.0},
        ],
        [{"role": "assistant", "text": "Got it.", "created_at": 12.0}],
    )
    assert cases_from_recording(folder) == []


def test_missing_recording_has_no_cases(tmp_path: Path) -> None:
    assert cases_from_recording(tmp_path) == []
