"""Per-turn timings, appended to recordings/<session_id>/turns.jsonl.

Each conversation message carries LiveKit's metrics for that turn: transcription delay,
end-of-turn delay, LLM time to first token, TTS time to first byte, end-to-end latency.
Writing them next to the recording makes a slow turn easy to find and listen to.
"""

import json
from pathlib import Path
from typing import Any

from livekit.agents.llm import ChatMessage


def turn_record(message: ChatMessage, turn_index: int) -> dict[str, Any]:
    return {
        "turn_index": turn_index,
        "role": message.role,
        "text": message.text_content or "",
        "interrupted": message.interrupted,
        "created_at": message.created_at,
        **dict(message.metrics),
    }


class TurnLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.turns = 0
        path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, message: ChatMessage) -> dict[str, Any]:
        if message.role == "user":
            self.turns += 1  # a turn starts with the caller speaking
        record = turn_record(message, self.turns)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
