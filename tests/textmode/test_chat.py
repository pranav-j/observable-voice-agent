"""The interactive chat loop, driven by scripted input and a scripted LLM."""

import pytest

from tests.textmode.fakes import GREETING, CountingStore, ScriptedLLM, call, reply
from voice_order.menu.models import Menu
from voice_order.textmode.agent import TextAgent
from voice_order.textmode.chat import HELP, run_chat
from voice_order.textmode.llm import LLMReply
from voice_order.tools.base import Session


class Terminal:
    """Feeds scripted lines to the chat and collects what it writes."""

    def __init__(self, *lines: str | None) -> None:
        self.lines = list(lines)
        self.prompts = 0
        self.out: list[str] = []

    async def read_line(self, prompt: str) -> str | None:
        self.prompts += 1
        return self.lines.pop(0) if self.lines else None

    def write(self, text: str) -> None:
        self.out.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.out)


@pytest.fixture
def store() -> CountingStore:
    return CountingStore()


def agent_with(menu: Menu, store: CountingStore, *replies: LLMReply) -> TextAgent:
    return TextAgent(
        llm=ScriptedLLM(*replies),
        session=Session.start(menu, "chat-test"),
        store=store,
        instructions="SYSTEM",
    )


async def test_greets_relays_and_hangs_up_on_quit(menu: Menu, store: CountingStore) -> None:
    agent = agent_with(menu, store, reply("Sure, what size?"))
    term = Terminal("A cappuccino", "/quit")
    turns = await run_chat(agent, GREETING, term.read_line, term.write)
    assert turns == 1
    assert term.out[:3] == [HELP, f"agent: {GREETING}", "agent: Sure, what size?"]
    assert "--- call ended ---" in term.text
    saved = await store.get("chat-test")
    assert saved is not None
    assert saved.status == "abandoned"


async def test_tool_calls_are_shown_unless_hidden(menu: Menu, store: CountingStore) -> None:
    script = (reply("", call("search_menu", query="dosa")), reply("We have dosas."))
    shown = Terminal("dosa?", "/quit")
    await run_chat(agent_with(menu, store, *script), GREETING, shown.read_line, shown.write)
    assert '  [tool] search_menu({"query": "dosa"}) -> masala_dosa (strong)' in shown.out

    hidden = Terminal("dosa?", "/quit")
    await run_chat(
        agent_with(menu, CountingStore(), *script),
        GREETING,
        hidden.read_line,
        hidden.write,
        show_tools=False,
    )
    assert not any("[tool]" in line for line in hidden.out)


async def test_order_command_shows_the_order_from_code(menu: Menu, store: CountingStore) -> None:
    agent = agent_with(
        menu, store, reply("", call("add_item", item_id="masala_dosa", quantity=2)), reply("Added.")
    )
    term = Terminal("two masala dosa", "/order", "/quit")
    await run_chat(agent, GREETING, term.read_line, term.write)
    assert "  1. Two Masala Dosa: 280 rupees" in term.text
    assert "  total: 280 rupees" in term.text


async def test_blank_lines_are_ignored(menu: Menu, store: CountingStore) -> None:
    agent = agent_with(menu, store)  # any LLM call would fail: nothing is scripted
    term = Terminal("", "   ", "/quit")
    assert await run_chat(agent, GREETING, term.read_line, term.write) == 0


async def test_end_of_input_hangs_up(menu: Menu, store: CountingStore) -> None:
    agent = agent_with(menu, store)
    term = Terminal()  # read_line returns None straight away
    await run_chat(agent, GREETING, term.read_line, term.write)
    assert agent.session.ending is not None
    assert agent.session.ending.reason == "caller hung up"


async def test_stops_when_the_agent_ends_the_call(menu: Menu, store: CountingStore) -> None:
    agent = agent_with(
        menu, store, reply("", call("end_call", reason="caller said bye")), reply("Goodbye!")
    )
    term = Terminal("bye", "this line is never read")
    await run_chat(agent, GREETING, term.read_line, term.write)
    assert term.prompts == 1
    assert "agent: Goodbye!" in term.out
    assert agent.session.ending is not None
    assert agent.session.ending.reason == "caller said bye"
