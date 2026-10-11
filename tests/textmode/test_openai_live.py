"""One real conversation turn against OpenAI. Needs OPENAI_API_KEY; skipped without it."""

import pytest

from voice_order.config import Settings
from voice_order.menu.models import Menu
from voice_order.prompts.loader import agent_system_prompt, greeting_prompt
from voice_order.store.base import InMemoryOrderStore
from voice_order.textmode.agent import TextAgent
from voice_order.textmode.openai_client import OpenAIClient
from voice_order.tools.base import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    if not s.has_openai_key:
        pytest.skip("OPENAI_API_KEY is not set")
    return s


async def test_agent_looks_up_the_menu_and_answers(menu: Menu, settings: Settings) -> None:
    agent = TextAgent(
        llm=OpenAIClient.from_settings(settings),
        session=Session.start(menu, "live-test"),
        store=InMemoryOrderStore(),
        instructions=agent_system_prompt(menu.restaurant).text,
    )
    await agent.start(greeting_prompt(menu.restaurant).text)
    turn = await agent.respond("Hi, do you have masala dosa?")

    # Wording varies run to run, so only check behavior the prompt requires.
    searches = [e for e in turn.tool_events if e.name == "search_menu"]
    assert searches, f"expected a menu lookup, got {[e.name for e in turn.tool_events]}"
    assert all(e.result["ok"] for e in searches)
    assert turn.text
    assert turn.usage.input_tokens > 0
