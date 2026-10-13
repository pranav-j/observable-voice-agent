"""Backend: join tokens for calls, the menu, and orders by session.

Run with `uvicorn voice_order.api.app:app` (or `make dev`).
"""

import json
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

from voice_order.api.limits import CallLimiter
from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu
from voice_order.store.base import OrderStore
from voice_order.store.postgres import PostgresOrderStore
from voice_order.tools.base import Session
from voice_order.tools.catalog import item_view, order_view

WEB_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the Vite dev server
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")


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


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The caller's address. Behind our proxy, that's the last X-Forwarded-For entry: the
    one the proxy added. Earlier entries come from the client and can be made up."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if trust_proxy and forwarded.strip():
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def create_app(
    settings: Settings | None = None,
    store: OrderStore | None = None,
    menu: Menu | None = None,
) -> FastAPI:
    """Build the app. Tests pass an in-memory store; the default connects to Postgres."""
    settings = settings or get_settings()
    menu = menu or load_menu()
    limiter = CallLimiter(settings.calls_per_ip_per_hour, settings.calls_per_day)

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
    def token(request: Request) -> TokenResponse:
        refusal = limiter.try_start(client_ip(request, settings.trust_proxy))
        if refusal is not None:
            raise HTTPException(
                status_code=429,
                detail=refusal.reason,
                headers={"Retry-After": str(refusal.retry_after_seconds)},
            )
        room, identity = new_call_ids()
        return TokenResponse(
            url=settings.livekit_public_url or settings.livekit_url,
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

    @app.get("/calls/{session_id}")
    async def get_call(session_id: str, request: Request) -> dict[str, Any]:
        """The end-of-call summary: final order, plus duration, turns and cost once saved."""
        if not SAFE_ID.fullmatch(session_id):  # it becomes a folder name below
            raise HTTPException(status_code=404, detail="no such call")
        order = await request.app.state.store.get(session_id)
        if order is None:
            raise HTTPException(status_code=404, detail=f"no call {session_id!r}")
        folder = Path(settings.recordings_dir) / session_id
        usage_file, turns_file = folder / "usage.json", folder / "turns.jsonl"
        usage = json.loads(usage_file.read_text()) if usage_file.exists() else None
        turns = 0
        if turns_file.exists():
            records = [json.loads(line) for line in turns_file.read_text().splitlines() if line]
            turns = max((r["turn_index"] for r in records), default=0)
        return {
            "session_id": session_id,
            "order": order_view(Session(menu=menu, order=order)),
            "saved": usage is not None,  # the worker writes usage.json when the call ends
            "duration_seconds": usage.get("duration_seconds") if usage else None,
            "turns": turns,
            "cost_usd": usage.get("total_cost_usd") if usage else None,
            "cost_is_estimate": bool(
                usage and any(m.get("estimated_from_call_length") for m in usage["models"])
            ),
        }

    return app


app = create_app()
