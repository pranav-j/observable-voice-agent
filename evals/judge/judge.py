"""The LLM judges: did the agent own up to a failed action, and did it give a discount?

Each judge is a versioned prompt plus a strict JSON answer. A reply that isn't valid
JSON with the expected field counts as no verdict, never as a pass or a fail.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from evals.judge.cases import ErrorCase
from voice_order.textmode.llm import LLMClient, Usage, UserMessage

ERROR_ACK_VERSION = "v1"
DISCOUNT_VERSION = "v1"
_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Verdict:
    value: bool | None  # None: the judge's answer couldn't be read
    reason: str
    usage: Usage


def _prompt(name: str, version: str) -> str:
    return (_DIR / f"{name}.{version}.md").read_text("utf-8").strip()


def parse_verdict(text: str, field: str) -> tuple[bool | None, str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group()) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get(field), bool):
        return None, f"unreadable judge reply: {text[:200]!r}"
    return data[field], str(data.get("reason", ""))


def error_ack_input(case: ErrorCase) -> str:
    detail = f"{case.error}: {case.message}" if case.message else case.error
    return (
        f"Action: {case.tool} {json.dumps(case.arguments, ensure_ascii=False)}\n"
        f"Result: failed with {detail}\n"
        f'What the order-taker said next: "{case.reply or "(nothing)"}"'
    )


async def judge_error_ack(case: ErrorCase, llm: LLMClient) -> Verdict:
    reply = await llm.complete(
        _prompt("error_ack", ERROR_ACK_VERSION), [UserMessage(error_ack_input(case))], []
    )
    value, reason = parse_verdict(reply.text, "acknowledged")
    return Verdict(value, reason, reply.usage)


async def judge_discount(agent_lines: list[str], llm: LLMClient) -> Verdict:
    said = "\n".join(f"- {line}" for line in agent_lines if line.strip()) or "(nothing)"
    reply = await llm.complete(
        _prompt("discount", DISCOUNT_VERSION),
        [UserMessage(f"Everything the order-taker said, in order:\n{said}")],
        [],
    )
    value, reason = parse_verdict(reply.text, "agreed_to_discount")
    return Verdict(value, reason, reply.usage)
