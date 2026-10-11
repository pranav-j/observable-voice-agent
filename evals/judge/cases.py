"""Moments worth judging: a tool failed, and the agent then said something to the caller.

Only errors the caller should hear about count. Turn-taking holds and read-back guards
are the agent talking to itself, and an error the agent fixed with a successful retry
before replying needed no apology.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from evals.text_run import TranscriptEntry

# Errors that are internal: the agent should just carry on, not tell the caller.
INTERNAL_ERRORS = frozenset(
    {
        "WAITING_FOR_CALLER",
        "READBACK_NOT_ANSWERED",
        "ORDER_NOT_CONFIRMED",
        "PHONE_MISSING",
        "READBACK_REQUIRED",
        "ORDER_INCOMPLETE",
        "INVALID_ARGUMENTS",
        "UNKNOWN_TOOL",
    }
)


class ErrorCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    index: int  # nth case in the call
    tool: str
    arguments: dict[str, Any]
    error: str
    message: str  # empty when only the code was kept (text-mode transcripts)
    reply: str  # what the agent said next, before the caller spoke again

    @property
    def case_id(self) -> str:
        return f"{self.session_id}#{self.index}"


def _caller_facing(error: str | None, tool: str, arguments: dict[str, Any]) -> bool:
    if not error or error in INTERNAL_ERRORS:
        return False
    # set_customer with a blank phone or name is the agent saving what it has so far,
    # before asking. The caller didn't say anything wrong, so there's nothing to tell them.
    blank = {"INVALID_PHONE": "phone", "INVALID_NAME": "name"}.get(error)
    return not (tool == "set_customer" and blank and not str(arguments.get(blank, "")).strip())


def _retried_ok(calls: list[dict[str, Any]], i: int, ok: Any) -> bool:
    name = calls[i]["name"]
    return any(c["name"] == name and ok(c) for c in calls[i + 1 :])


def cases_from_transcript(session_id: str, transcript: list[TranscriptEntry]) -> list[ErrorCase]:
    """Text mode: each agent turn has its tool calls, and its text is the reply."""
    cases: list[ErrorCase] = []
    for entry in transcript:
        if entry.speaker != "agent":
            continue
        calls = entry.tool_calls
        for i, call in enumerate(calls):
            arguments = call.get("arguments") or {}
            if call.get("ok") or not _caller_facing(call.get("error"), call["name"], arguments):
                continue
            if _retried_ok(calls, i, lambda c: bool(c.get("ok"))):
                continue
            cases.append(
                ErrorCase(
                    session_id=session_id,
                    index=len(cases),
                    tool=call["name"],
                    arguments=arguments,
                    error=str(call["error"]),
                    message="",
                    reply=entry.text,
                )
            )
    return cases


def cases_from_recording(folder: Path) -> list[ErrorCase]:
    """Voice: the worker's tool log, and what the agent said before the caller's next turn."""
    calls_path, transcript_path = folder / "tool_calls.jsonl", folder / "transcript.json"
    if not (calls_path.exists() and transcript_path.exists()):
        return []
    calls = [json.loads(line) for line in calls_path.read_text().splitlines() if line.strip()]
    rows: list[dict[str, Any]] = json.loads(transcript_path.read_text())

    def ok(c: dict[str, Any]) -> bool:
        return bool((c.get("result") or {}).get("ok"))

    cases: list[ErrorCase] = []
    for i, call in enumerate(calls):
        result = call.get("result") or {}
        arguments = call.get("arguments") or {}
        if ok(call) or not _caller_facing(result.get("error"), call["name"], arguments):
            continue
        t = call.get("created_at", 0.0)
        next_caller = min(
            (r["created_at"] for r in rows if r["role"] == "user" and r["created_at"] > t),
            default=float("inf"),
        )
        later = [c for c in calls[i + 1 :] if c.get("created_at", 0.0) < next_caller]
        if any(c["name"] == call["name"] and ok(c) for c in later):
            continue
        reply = " ".join(
            r["text"]
            for r in rows
            if r["role"] == "assistant" and t < r["created_at"] < next_caller
        )
        cases.append(
            ErrorCase(
                session_id=folder.name,
                index=len(cases),
                tool=call["name"],
                arguments=arguments,
                error=str(result["error"]),
                message=str(result.get("message", "")),
                reply=reply,
            )
        )
    return cases
