"""Turn-taking rules shared by every runtime (text loop and voice worker).

When the agent asks the caller something, its turn should end there so the caller can
answer. Without this, the model would carry on in the same turn as if it had heard a
reply: retrying with made-up details, ending the call, or transferring it.
"""

from voice_order.tools.base import Result

# How many tool rounds one agent turn may take before it has to answer. A two-item order
# can need four (search, add, search, add) when the model makes the calls one at a time.
MAX_TOOL_ROUNDS = 8

# These must wait for the caller's answer if the agent has just asked something.
# Order changes in the same reply still run ("I've added it. Anything else?").
WAIT_FOR_ANSWER = frozenset({"get_readback", "confirm_order", "end_call", "transfer_to_human"})

WAITING_FOR_CALLER: Result = {
    "ok": False,
    "error": "WAITING_FOR_CALLER",
    "message": (
        "Not run: you asked the caller a question in this reply. "
        "Wait for their answer, then call it again if it's still needed."
    ),
}


def asks_caller(text: str) -> bool:
    """The agent's words in this step include a question to the caller."""
    return "?" in text
