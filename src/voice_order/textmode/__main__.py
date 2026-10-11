"""`python -m voice_order.textmode` (or `make chat`): talk to the agent in your terminal."""

import argparse
import asyncio
import secrets
import sys
from datetime import datetime

import psycopg
from psycopg_pool import PoolTimeout

from voice_order.config import get_settings
from voice_order.menu.loader import load_menu
from voice_order.prompts.loader import agent_system_prompt, greeting_prompt
from voice_order.store.base import InMemoryOrderStore, OrderStore
from voice_order.store.postgres import PostgresOrderStore
from voice_order.textmode.agent import TextAgent
from voice_order.textmode.chat import run_chat
from voice_order.textmode.openai_client import OpenAIClient
from voice_order.tools.base import Session


async def read_stdin(prompt: str) -> str | None:
    try:
        return await asyncio.to_thread(input, prompt)
    except EOFError:
        return None


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Talk to the order agent as the caller.")
    parser.add_argument("--memory", action="store_true", help="don't save orders to Postgres")
    parser.add_argument("--no-tools", action="store_true", help="hide tool calls")
    parser.add_argument("--model", help="override LLM_MODEL for this chat")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.has_openai_key:
        print("OPENAI_API_KEY is not set. Add it to .env (see .env.example).", file=sys.stderr)
        return 2

    pg: PostgresOrderStore | None = None
    store: OrderStore
    if args.memory:
        store = InMemoryOrderStore()
    else:
        try:
            pg = store = await PostgresOrderStore.connect(settings.database_url, connect_timeout=3)
        except (PoolTimeout, psycopg.OperationalError):
            print("Can't reach Postgres. Run `make up`, or use --memory.", file=sys.stderr)
            return 2

    menu = load_menu()
    session_id = f"chat-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    agent = TextAgent(
        llm=OpenAIClient.from_settings(settings, model=args.model),
        session=Session.start(menu, session_id),
        store=store,
        instructions=agent_system_prompt(menu.restaurant).text,
    )
    store_name = "memory" if pg is None else "postgres"
    print(f"session {session_id} | model {agent.llm.model} | store {store_name}")
    try:
        await run_chat(
            agent,
            greeting_prompt(menu.restaurant).text,
            read_stdin,
            print,
            show_tools=not args.no_tools,
            color=sys.stdout.isatty(),
        )
    finally:
        if pg is not None:
            await pg.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted (use /quit to hang up cleanly)")
        sys.exit(130)
