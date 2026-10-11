"""Scripted LLM replies for a full happy-path call, shared by eval tests."""

from tests.textmode.fakes import call, reply

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
    reply("", call("set_customer", name="Priya", phone="9000000002"), call("get_readback")),
    reply("Let me read that back. Is that correct?"),
    reply("", call("confirm_order")),
    reply("It'll be ready for pickup. Goodbye!"),
]
HAPPY_CALLER = [
    reply("One large cold coffee with oat milk, please.", tokens=(40, 9)),
    reply("Priya, 9000000002."),
    reply("Yes, that's right."),
    reply("Thanks, bye! [END]"),
]
