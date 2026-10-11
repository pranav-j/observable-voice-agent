"""Interactive text chat: you play the caller, the real agent answers.

The loop takes its input and output as functions, so tests can drive it with scripts.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from voice_order.textmode.agent import TextAgent
from voice_order.tools.base import Result
from voice_order.tools.catalog import order_view

ReadLine = Callable[[str], Awaitable[str | None]]  # returns None at end of input
Write = Callable[[str], None]

HELP = "Type as the caller. /order shows the order, /quit hangs up."


async def run_chat(
    agent: TextAgent,
    greeting: str,
    read_line: ReadLine,
    write: Write,
    *,
    show_tools: bool = True,
    color: bool = False,
) -> int:
    """Run until the agent ends the call or the caller quits. Returns the number of turns."""
    dim = (lambda s: f"\033[2m{s}\033[0m") if color else (lambda s: s)
    write(dim(HELP))
    write(f"agent: {await agent.start(greeting)}")
    turns = 0
    while agent.session.ending is None:
        line = await read_line("you: ")
        text = (line or "").strip()
        if line is None or text == "/quit":
            await agent.hang_up("caller hung up")
            break
        if not text:
            continue
        if text == "/order":
            write(dim(describe_order(order_view(agent.session))))
            continue
        turn = await agent.respond(text)
        turns += 1
        if show_tools:
            for event in turn.tool_events:
                write(dim(f"  [tool] {event.name}({event.arguments}) -> {brief(event.result)}"))
        write(f"agent: {turn.text}")

    view = order_view(agent.session)
    write(dim("--- call ended ---"))
    write(dim(describe_order(view)))
    usage = agent.usage
    write(dim(f"turns: {turns}, tokens: {usage.input_tokens} in / {usage.output_tokens} out"))
    return turns


def brief(result: Result) -> str:
    if not result.get("ok"):
        return str(result.get("error"))
    if "matches" in result:
        top = result["matches"][0]
        return f"{top['item_id']} ({top['match']})"
    return "ok"


def describe_order(view: dict[str, Any]) -> str:
    lines = [f"  {x['line_id']}. {x['description']}: {x['line_total']}" for x in view["lines"]]
    customer = view["customer"]
    who = f"{customer['name']}, {customer['phone']}" if customer else "not set"
    return "\n".join(
        [
            f"order ({view['status']}):",
            *(lines or ["  (no items)"]),
            f"  total: {view['total']}",
            f"  customer: {who}",
        ]
    )
