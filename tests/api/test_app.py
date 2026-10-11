"""The backend API, with an in-memory store: no Postgres, no LiveKit server needed."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from livekit import api

from voice_order.api.app import create_app
from voice_order.config import Settings
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.base import InMemoryOrderStore

SETTINGS = Settings(
    _env_file=None,
    livekit_api_key="testkey",
    livekit_api_secret="test-secret-that-is-at-least-32-bytes-long",
)


@pytest.fixture
def store() -> InMemoryOrderStore:
    return InMemoryOrderStore()


@pytest.fixture
def client(store: InMemoryOrderStore, menu: Menu) -> Iterator[TestClient]:
    with TestClient(create_app(settings=SETTINGS, store=store, menu=menu)) as c:
        yield c


def test_token_joins_a_new_room_and_dispatches_the_agent(client: TestClient) -> None:
    body = client.post("/token").json()
    assert body["url"] == SETTINGS.livekit_url
    assert body["room"].startswith("call-")
    claims = api.TokenVerifier("testkey", "test-secret-that-is-at-least-32-bytes-long").verify(
        body["token"]
    )
    assert claims.identity == body["identity"]
    assert claims.video is not None
    assert (claims.video.room_join, claims.video.room) == (True, body["room"])
    assert claims.room_config is not None
    assert [a.agent_name for a in claims.room_config.agents] == ["order-agent"]


def test_every_call_gets_its_own_room(client: TestClient) -> None:
    rooms = {client.post("/token").json()["room"] for _ in range(5)}
    assert len(rooms) == 5


def test_menu(client: TestClient) -> None:
    body = client.get("/menu").json()
    assert body["restaurant"] == "Juniper Street Kitchen"
    coffee = next(i for i in body["items"] if i["item_id"] == "cold_coffee")
    assert coffee["sizes"][0]["price"] == "180 rupees"


async def test_order_by_session(client: TestClient, store: InMemoryOrderStore, menu: Menu) -> None:
    assert client.get("/orders/nope").status_code == 404
    order = state.add_line(state.new_order("call-1"), menu, "masala_dosa", 2)
    await store.save(order)
    view = client.get("/orders/call-1").json()
    assert view["lines"][0]["description"] == "Two Masala Dosa"
    assert view["total"] == "280 rupees"


def test_web_dev_server_may_call_the_api(client: TestClient) -> None:
    response = client.options(
        "/token",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_call_summary_before_and_after_the_recording_is_saved(
    store: InMemoryOrderStore, menu: Menu, tmp_path: Path
) -> None:
    settings = SETTINGS.model_copy(update={"recordings_dir": str(tmp_path)})
    order = state.add_line(state.new_order("call-2"), menu, "affogato", 1)
    await store.save(order)
    with TestClient(create_app(settings=settings, store=store, menu=menu)) as client:
        assert client.get("/calls/nope").status_code == 404
        early = client.get("/calls/call-2").json()
        assert (early["saved"], early["cost_usd"], early["turns"]) == (False, None, 0)
        folder = tmp_path / "call-2"
        folder.mkdir()
        (folder / "usage.json").write_text(
            json.dumps(
                {
                    "total_cost_usd": 0.0123,
                    "duration_seconds": 61.5,
                    "models": [{"estimated_from_call_length": True}],
                }
            )
        )
        (folder / "turns.jsonl").write_text(
            "\n".join(json.dumps({"turn_index": i, "role": "user"}) for i in (1, 2, 3)) + "\n"
        )
        done = client.get("/calls/call-2").json()
    assert (done["saved"], done["turns"], done["duration_seconds"]) == (True, 3, 61.5)
    assert (done["cost_usd"], done["cost_is_estimate"]) == (0.0123, True)
    assert done["order"]["lines"][0]["description"] == "One Affogato"


@pytest.mark.parametrize("bad", ["..", "call-1.json", "a b"])
def test_call_ids_that_could_escape_the_recordings_folder_are_rejected(
    client: TestClient, bad: str
) -> None:
    assert client.get(f"/calls/{bad}").status_code == 404
