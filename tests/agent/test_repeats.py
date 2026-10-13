"""Dropping a sentence the LLM repeated back to back in one reply."""

from collections.abc import AsyncIterator

from livekit.agents.llm import ChatChunk, ChoiceDelta, FunctionToolCall

from voice_order.agent.repeats import without_repeats


async def _stream(*items: object) -> AsyncIterator[object]:
    for item in items:
        yield item


async def _said(*items: object) -> str:
    return "".join(
        x for x in [c async for c in without_repeats(_stream(*items))] if isinstance(x, str)
    )


async def test_a_question_said_twice_is_said_once() -> None:
    doubled = (
        "What name should I",
        " put on the order?",
        "What name should",
        " I put on the order?",
    )
    assert await _said(*doubled) == "What name should I put on the order?"


async def test_different_sentences_all_pass() -> None:
    assert await _said("Sure, one coffee.", " Anything else?") == "Sure, one coffee. Anything else?"


async def test_repeats_match_ignoring_case_and_spacing() -> None:
    assert await _said("Anything else?", " anything  else?") == "Anything else?"


async def test_the_same_sentence_later_in_the_reply_is_kept() -> None:
    reply = ("Got it.", " One coffee.", " Got it.")
    assert await _said(*reply) == "Got it. One coffee. Got it."


async def test_text_without_an_ending_still_comes_out() -> None:
    assert await _said("Thank you", " for calling") == "Thank you for calling"


async def test_tool_calls_pass_through_in_order() -> None:
    call = ChatChunk(
        id="r",
        delta=ChoiceDelta(
            role="assistant",
            tool_calls=[FunctionToolCall(name="add_item", arguments="{}", call_id="c1")],
        ),
    )
    out = [c async for c in without_repeats(_stream("One moment", call, "Done."))]
    assert out == ["One moment", call, "Done."]


async def test_text_chunks_from_the_llm_are_read_too() -> None:
    def text(t: str) -> ChatChunk:
        return ChatChunk(id="r", delta=ChoiceDelta(role="assistant", content=t))

    assert await _said(text("Anything else?"), text("Anything else?")) == "Anything else?"


async def test_a_repeat_across_two_message_items_is_dropped() -> None:
    # What the plugin streams: the first item's text, a marker when that item ends, the
    # second item's text.
    marker = ChatChunk(
        id="r", delta=ChoiceDelta(role="assistant", extra={"openai": {"phase": "commentary"}})
    )
    out = [c async for c in without_repeats(_stream("Anything else?", marker, "Anything else?"))]
    assert out == ["Anything else?", marker]
