"""Scripted LLM replies for a full happy-path call, shared by eval tests."""

from tests.textmode.fakes import call, readback_text, reply

HAPPY_READBACK = readback_text(
    ("cold_coffee", 1, "large", ["oat_milk"]), name="Priya", phone="9876523456"
)

HAPPY_AGENT = [
    reply(
        "",
        call(
            "add_item",
            item_id="cold_coffee",
            quantity=1,
            size_id="large",
            modifier_ids=["oat_milk"],
        ),
    ),
    reply("Got it. Your name and number?", tokens=(100, 10)),
    reply("", call("set_customer", name="Priya", phone="9876523456"), call("get_readback")),
    reply(HAPPY_READBACK),
    reply("", call("confirm_order")),
    reply("It'll be ready for pickup. Goodbye!"),
]
HAPPY_CALLER = [
    reply("One large cold coffee with oat milk, please.", tokens=(40, 9)),
    reply("Priya, 9876523456."),
    reply("Yes, that's right."),
    reply("Thanks, bye! [END]"),
]
