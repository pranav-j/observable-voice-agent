"""Tool plumbing: the session tools act on, the Tool type, and dispatch.

Tools are the only way the LLM touches order state. Every call returns a plain dict:
{"ok": true, ...} on success, or {"ok": false, "error": CODE, "message": ...} on failure.
Errors are data, never exceptions, so the LLM can read them and recover.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from voice_order.menu.models import Menu
from voice_order.order.errors import OrderError
from voice_order.order.models import Order
from voice_order.order.readback import said_in_full
from voice_order.order.state import new_order

Result = dict[str, Any]
ArgsT = TypeVar("ArgsT", bound=BaseModel)


EndKind = Literal["end_call", "transfer"]


@dataclass(frozen=True)
class CallEnd:
    kind: EndKind
    reason: str


@dataclass
class Session:
    """One call. The order is immutable; tools replace it with each new version.

    `ending` is set by end_call or transfer_to_human. Whatever runs the conversation
    (text loop or voice worker) checks it and wraps up after the agent's last words.

    Whatever runs the conversation also calls `caller_spoke()` on every caller utterance
    and `agent_said()` whenever the agent finishes saying something, so tools can tell
    whether the caller heard the read-back in full and replied to it.
    """

    menu: Menu
    order: Order
    ending: CallEnd | None = None
    caller_turns: int = 0
    readback_caller_turn: int | None = None  # caller_turns when the read-back was heard
    readback_text: str | None = None  # fetched by get_readback, not yet said in full
    end_call_held: bool = False  # end_call was held once to remind the agent to confirm
    phone_digits: str = ""  # the start of a phone number the caller is giving in parts

    def caller_spoke(self) -> None:
        self.caller_turns += 1

    def agent_said(self, text: str, *, interrupted: bool = False) -> None:
        """The agent finished saying `text`: what was actually played, if interrupted.

        Fetching the read-back isn't the same as saying it. In a voice call the caller can
        cut in before a word of it is spoken, so it only counts once it was said in full.
        """
        readback = self.readback_text
        if readback is not None and said_in_full(text, readback, cut_off=interrupted):
            self.readback_caller_turn = self.caller_turns
            self.readback_text = None

    @property
    def readback_answered(self) -> bool:
        return (
            self.readback_caller_turn is not None and self.caller_turns > self.readback_caller_turn
        )

    @classmethod
    def start(cls, menu: Menu, session_id: str) -> "Session":
        return cls(menu=menu, order=new_order(session_id))


class ToolArgs(BaseModel):
    # Lax types ("2" is accepted for 2), but unknown argument names are an error.
    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


@dataclass(frozen=True)
class Tool(Generic[ArgsT]):
    name: str
    description: str
    args_model: type[ArgsT]
    handler: Callable[[Session, ArgsT], Result]

    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for the arguments, generated from the same model that validates them."""
        return self.args_model.model_json_schema()


def ok(**payload: Any) -> Result:
    return {"ok": True, **payload}


def error(code: str, message: str, **extra: Any) -> Result:
    return {"ok": False, "error": code, "message": message, **extra}


def dispatch(
    session: Session,
    tools: Mapping[str, Tool[Any]],
    name: str,
    arguments: str | Mapping[str, Any],
) -> Result:
    """Validate the arguments, run the tool, and turn domain errors into error results.

    `arguments` may be the raw JSON string an LLM produced, or an already-parsed dict.
    Unexpected exceptions are bugs and are left to propagate.
    """
    tool = tools.get(name)
    if tool is None:
        return error("UNKNOWN_TOOL", f"No tool named {name!r}. Tools: {', '.join(tools)}.")
    try:
        if isinstance(arguments, str):
            args = tool.args_model.model_validate_json(arguments or "{}")
        else:
            args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        return error("INVALID_ARGUMENTS", _describe(exc))
    try:
        return tool.handler(session, args)
    except OrderError as exc:
        alternatives = [
            {"item_id": item.id, "name": item.name}
            for item in (session.menu.item(i) for i in exc.alternatives)
            if item is not None
        ]
        extra = {"alternatives": alternatives} if alternatives else {}
        return error(exc.code, exc.message, **extra)


def _describe(exc: ValidationError) -> str:
    problems = []
    for e in exc.errors():
        where = ".".join(str(part) for part in e["loc"]) or "arguments"
        problems.append(f"{where}: {e['msg']}")
    return "; ".join(problems)


def to_json(result: Result) -> str:
    """Compact JSON for sending a result back to an LLM."""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
