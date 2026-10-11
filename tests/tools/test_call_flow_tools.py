"""get_readback, confirm_order, transfer_to_human, end_call, and full flows through dispatch."""

from typing import Any

import pytest

from voice_order.order import state
from voice_order.tools.base import CallEnd, Session, dispatch
from voice_order.tools.catalog import TOOLS


def call(session: Session, tool: str, /, **arguments: Any) -> dict[str, Any]:
    return dispatch(session, TOOLS, tool, arguments)


def read_back(session: Session) -> dict[str, Any]:
    """Fetch the read-back and have the agent say it in full, as the runtimes report."""
    result = call(session, "get_readback")
    session.agent_said(result["readback"])
    return result


@pytest.fixture
def ready(session: Session) -> Session:
    """Items and customer in place, no read-back yet."""
    call(session, "add_item", item_id="masala_dosa", quantity=2)
    call(session, "set_customer", name="Anil", phone="9000000001")
    return session


def test_the_agent_has_exactly_these_tools() -> None:
    assert set(TOOLS) == {
        "search_menu",
        "add_item",
        "update_item",
        "remove_item",
        "set_customer",
        "get_order_summary",
        "get_readback",
        "confirm_order",
        "transfer_to_human",
        "end_call",
    }


# --- get_readback ---------------------------------------------------------------------


def test_readback_returns_text_and_records_the_sequence(ready: Session) -> None:
    result = call(ready, "get_readback")
    assert result["readback"] == (
        "Let me read that back. Two Masala Dosa. Your total is 280 rupees. "
        "The order is for Anil, phone number 90000 00001. Is that correct?"
    )
    assert "word for word" in result["instructions"]
    assert ready.order.readback_seq == ready.order.mutation_seq


def test_incomplete_order_gets_no_readback(session: Session) -> None:
    call(session, "add_item", item_id="masala_dosa", quantity=1)
    before = session.order
    result = call(session, "get_readback")
    assert result["error"] == "ORDER_INCOMPLETE"
    assert "name and phone number" in result["message"]
    assert session.order is before  # nothing recorded


# --- confirm_order ---------------------------------------------------------------------


def test_confirm_without_readback_is_refused(ready: Session) -> None:
    result = call(ready, "confirm_order")
    assert result["error"] == "READBACK_REQUIRED"
    assert ready.order.status == "draft"


def test_happy_path_through_dispatch_only(session: Session) -> None:
    assert (
        call(session, "search_menu", query="cold coffee")["matches"][0]["item_id"] == "cold_coffee"
    )
    call(session, "add_item", item_id="cold_coffee", quantity=1, size_id="large")
    call(session, "set_customer", name="Anil", phone="90000 00001")
    read_back(session)
    session.caller_spoke()  # "yes, that's right"
    result = call(session, "confirm_order")
    assert result["ok"] is True
    assert result["order"]["status"] == "confirmed"
    assert "end_call" in result["instructions"]


def test_change_after_readback_needs_a_new_readback(ready: Session) -> None:
    read_back(ready)
    call(ready, "add_item", item_id="affogato", quantity=1)
    assert call(ready, "confirm_order")["error"] == "READBACK_REQUIRED"
    assert "Affogato" in read_back(ready)["readback"]
    ready.caller_spoke()
    assert call(ready, "confirm_order")["order"]["status"] == "confirmed"


def test_readback_after_confirmation_is_refused(ready: Session) -> None:
    read_back(ready)
    ready.caller_spoke()
    call(ready, "confirm_order")
    assert call(ready, "get_readback")["error"] == "ORDER_CLOSED"
    assert call(ready, "confirm_order")["error"] == "ORDER_CLOSED"


# --- transfer_to_human and end_call -------------------------------------------------------


def test_transfer_escalates_and_flags_the_session(ready: Session) -> None:
    result = call(ready, "transfer_to_human", reason="asked for a person twice")
    assert result["status"] == "escalated"
    assert ready.ending == CallEnd(kind="transfer", reason="asked for a person twice")


def test_end_call_abandons_an_unconfirmed_order(ready: Session) -> None:
    result = call(ready, "end_call", reason="caller hung up")
    assert result["status"] == "abandoned"
    assert ready.ending == CallEnd(kind="end_call", reason="caller hung up")


def test_end_call_keeps_a_confirmed_order(ready: Session) -> None:
    read_back(ready)
    ready.caller_spoke()
    call(ready, "confirm_order")
    assert call(ready, "end_call", reason="done")["status"] == "confirmed"
    assert call(ready, "transfer_to_human", reason="question")["status"] == "confirmed"


def test_first_ending_wins(ready: Session) -> None:
    call(ready, "end_call", reason="first")
    call(ready, "transfer_to_human", reason="second")
    assert ready.ending == CallEnd(kind="end_call", reason="first")


def test_no_changes_after_the_call_ends(ready: Session) -> None:
    call(ready, "end_call", reason="caller hung up")
    assert call(ready, "add_item", item_id="affogato", quantity=1)["error"] == "ORDER_CLOSED"


@pytest.mark.parametrize("tool", ["transfer_to_human", "end_call"])
@pytest.mark.parametrize("arguments", [{}, {"reason": "  "}])
def test_reason_is_required(ready: Session, tool: str, arguments: dict[str, Any]) -> None:
    assert call(ready, tool, **arguments)["error"] == "INVALID_ARGUMENTS"
    assert ready.ending is None


def test_a_fresh_session_has_no_ending(session: Session) -> None:
    assert session.ending is None
    assert state.new_order("x").status == "draft"


# --- the caller must reply to the read-back --------------------------------------------------


def test_confirm_right_after_the_readback_is_refused(ready: Session) -> None:
    read_back(ready)
    result = call(ready, "confirm_order")
    assert result["error"] == "READBACK_NOT_ANSWERED"
    assert ready.order.status == "draft"


def test_confirm_works_once_the_caller_has_replied(ready: Session) -> None:
    read_back(ready)
    ready.caller_spoke()
    assert call(ready, "confirm_order")["order"]["status"] == "confirmed"


def test_a_new_readback_needs_a_new_reply(ready: Session) -> None:
    read_back(ready)
    ready.caller_spoke()
    read_back(ready)  # read it back again, e.g. after a question
    assert call(ready, "confirm_order")["error"] == "READBACK_NOT_ANSWERED"


def test_a_stale_readback_still_says_the_order_changed(ready: Session) -> None:
    read_back(ready)
    call(ready, "add_item", item_id="affogato", quantity=1)
    ready.caller_spoke()
    assert call(ready, "confirm_order")["error"] == "READBACK_REQUIRED"


# --- the read-back has to be heard, not just fetched -----------------------------------------


def test_a_readback_that_was_never_said_does_not_count(ready: Session) -> None:
    # Voice: the caller cut in before any of it played, then said "that's right".
    call(ready, "get_readback")
    ready.caller_spoke()
    result = call(ready, "confirm_order")
    assert result["error"] == "READBACK_NOT_ANSWERED"
    assert "said in full" in result["message"]


def test_an_interrupted_readback_does_not_count(ready: Session) -> None:
    text = call(ready, "get_readback")["readback"]
    ready.agent_said(text[: len(text) * 9 // 10], interrupted=True)  # cut off near the end
    ready.caller_spoke()
    assert call(ready, "confirm_order")["error"] == "READBACK_NOT_ANSWERED"


def test_a_late_interrupted_flag_on_a_finished_readback_still_counts(ready: Session) -> None:
    # LiveKit can flag the speech as interrupted after it finished playing, when the
    # caller speaks while a held-back tool call kept it open. The text shows it all played.
    text = call(ready, "get_readback")["readback"]
    ready.agent_said(text, interrupted=True)
    ready.caller_spoke()
    assert call(ready, "confirm_order")["order"]["status"] == "confirmed"


def test_other_words_before_the_readback_do_not_count(ready: Session) -> None:
    call(ready, "get_readback")
    ready.agent_said("Sure, one moment.")  # said in the same step as the tool call
    ready.caller_spoke()
    assert call(ready, "confirm_order")["error"] == "READBACK_NOT_ANSWERED"


def test_a_readback_said_with_small_slips_counts(ready: Session) -> None:
    text = call(ready, "get_readback")["readback"]
    ready.agent_said("Okay! " + text.replace("Let me read that back.", "Here's your order:"))
    ready.caller_spoke()
    assert call(ready, "confirm_order")["order"]["status"] == "confirmed"
