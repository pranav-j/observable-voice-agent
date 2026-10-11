"""Backend: join tokens for calls, the menu, and orders by session.

Run with `uvicorn voice_order.api.app:app` (or `make dev`).
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu
from voice_order.store.base import OrderStore
from voice_order.store.postgres import PostgresOrderStore
from voice_order.tools.base import Session
from voice_order.tools.catalog import item_view, order_view

WEB_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the Vite dev server


class TokenResponse(BaseModel):
    url: str
    token: str
    room: str  # also the session id the order is stored under
    identity: str


def new_call_ids() -> tuple[str, str]:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"call-{stamp}-{secrets.token_hex(3)}", f"caller-{secrets.token_hex(3)}"


def join_token(settings: Settings, room: str, identity: str) -> str:
    """A token to join `room` that also asks LiveKit to dispatch our agent into it."""
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret.get_secret_value())
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)])
        )
        .to_jwt()
    )


def create_app(
    settings: Settings | None = None,
    store: OrderStore | None = None,
    menu: Menu | None = None,
) -> FastAPI:
    """Build the app. Tests pass an in-memory store; the default connects to Postgres."""
    settings = settings or get_settings()
    menu = menu or load_menu()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if store is not None:
            app.state.store = store
            yield
            return
        async with await PostgresOrderStore.connect(settings.database_url) as pg:
            app.state.store = pg
            yield

    app = FastAPI(title="voice-order-agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=WEB_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )

    @app.post("/token")
    def token() -> TokenResponse:
        room, identity = new_call_ids()
        return TokenResponse(
            url=settings.livekit_url,
            token=join_token(settings, room, identity),
            room=room,
            identity=identity,
        )

    @app.get("/menu")
    def get_menu() -> dict[str, Any]:
        return {"restaurant": menu.restaurant, "items": [item_view(i) for i in menu.items]}

    @app.get("/orders/{session_id}")
    async def get_order(session_id: str, request: Request) -> dict[str, Any]:
        order = await request.app.state.store.get(session_id)
        if order is None:
            raise HTTPException(status_code=404, detail=f"no order for session {session_id!r}")
        return order_view(Session(menu=menu, order=order))

    return app


app = create_app()
