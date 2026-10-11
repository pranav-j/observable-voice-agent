"""dispatch: argument validation, unknown tools, and domain errors returned as data."""

from typing import Any

import pytest
from pydantic import Field

from voice_order.order.errors import ErrorCode, OrderError
from voice_order.tools.base import Result, Session, Tool, ToolArgs, dispatch, ok, to_json
from voice_order.tools.catalog import TOOLS


class EchoArgs(ToolArgs):
    quantity: int = Field(ge=1)


def echo(session: Session, args: EchoArgs) -> Result:
    return ok(quantity=args.quantity)


def out_of_stock(session: Session, args: EchoArgs) -> Result:
    raise OrderError(
        ErrorCode.OUT_OF_STOCK, "Mango Lassi is out of stock.", ("sweet_lassi", "not_a_real_item")
    )


FAKE: dict[str, Tool[Any]] = {
    "echo": Tool("echo", "Echo the quantity.", EchoArgs, echo),
    "out_of_stock": Tool("out_of_stock", "Always fails.", EchoArgs, out_of_stock),
}


def test_accepts_parsed_and_raw_json_arguments(session: Session) -> None:
    assert dispatch(session, FAKE, "echo", {"quantity": 2}) == {"ok": True, "quantity": 2}
    assert dispatch(session, FAKE, "echo", '{"quantity": 2}') == {"ok": True, "quantity": 2}


def test_lax_types_accept_numeric_strings(session: Session) -> None:
    assert dispatch(session, FAKE, "echo", {"quantity": "3"})["quantity"] == 3


def test_unknown_tool(session: Session) -> None:
    result = dispatch(session, FAKE, "make_coffee", {})
    assert result["error"] == "UNKNOWN_TOOL"
    assert "echo, out_of_stock" in result["message"]


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        ({}, "quantity: Field required"),
        ({"quantity": 0}, "quantity: Input should be greater than or equal to 1"),
        ({"quantity": "two"}, "quantity: Input should be a valid integer"),
        ({"quantity": 1, "size": "large"}, "size: Extra inputs are not permitted"),
        ("{not json", "Invalid JSON"),
    ],
)
def test_invalid_arguments_are_explained(session: Session, arguments: Any, fragment: str) -> None:
    result = dispatch(session, FAKE, "echo", arguments)
    assert (result["ok"], result["error"]) == (False, "INVALID_ARGUMENTS")
    assert fragment in result["message"]


def test_empty_raw_arguments_mean_no_arguments(session: Session) -> None:
    result = dispatch(session, TOOLS, "get_order_summary", "")
    assert result["ok"] is True


def test_domain_errors_become_data_with_named_alternatives(session: Session) -> None:
    result = dispatch(session, FAKE, "out_of_stock", {"quantity": 1})
    assert result == {
        "ok": False,
        "error": "OUT_OF_STOCK",
        "message": "Mango Lassi is out of stock.",
        "alternatives": [{"item_id": "sweet_lassi", "name": "Sweet Lassi"}],
    }


def test_results_serialize_compactly() -> None:
    assert to_json({"ok": True, "total": "₹190"}) == '{"ok":true,"total":"₹190"}'


# --- the real catalog --------------------------------------------------------------


def test_registry_keys_match_tool_names() -> None:
    assert all(name == tool.name for name, tool in TOOLS.items())


@pytest.mark.parametrize("name", list(TOOLS))
def test_every_tool_has_a_description_and_strict_schema(name: str) -> None:
    tool = TOOLS[name]
    assert len(tool.description) > 40
    schema = tool.parameters_schema()
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is False
    for prop in schema.get("properties", {}).values():
        assert prop.get("description"), f"{name}: every argument needs a description"
