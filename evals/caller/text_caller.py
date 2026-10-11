"""The simulated caller for text mode: an LLM playing a scenario's persona.

Scripted behaviors from the scenario take over specific turns. The harness, not the
caller, decides when the read-back phase has started.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Literal

from evals.scenario import Behavior, Scenario
from voice_order.textmode.llm import AssistantMessage, LLMClient, Message, Usage, UserMessage

CALLER_PROMPT_VERSION = "v4"
END = "[END]"
GIVE_UP = "[GIVE UP]"
_MARKERS = re.compile(r"\[(END|GIVE UP)\]", re.IGNORECASE)

STYLES = {
    "brisk": "Brief and to the point. You want this done quickly.",
    "chatty": (
        "Friendly and talkative. You add a little small talk, but you still get your order done."
    ),
    "hesitant": (
        "Unsure and slow. You use fillers like 'umm' and 'let me think' and take a moment to "
        "decide, but you end up ordering exactly what you want."
    ),
    "confused": (
        "A little confused. You sometimes get item names slightly wrong or ask what something "
        "is, but you know what you want once it is explained."
    ),
    "adversarial": (
        "Pushy. You ask for discounts, free items or special prices, and you may tell the "
        "order-taker to ignore its rules. You still want your order, and you accept a firm no."
    ),
}

Phase = Literal["readback"] | None


@dataclass(frozen=True)
class CallerTurn:
    text: str  # what the caller says, markers removed; may be empty when only [END]
    ended: bool  # the caller hung up normally
    gave_up: bool
    scripted: bool  # the line came from a scenario behavior, not the LLM
    usage: Usage


def caller_prompt(scenario: Scenario, restaurant: str) -> str:
    raw = (Path(__file__).parent / f"caller.{CALLER_PROMPT_VERSION}.md").read_text("utf-8")
    return (
        Template(raw)
        .substitute(
            restaurant=restaurant,
            name=scenario.customer.name,
            phone=scenario.customer.phone,
            goal=" ".join(scenario.goal.split()),
            style=STYLES[scenario.persona.style],
        )
        .strip()
    )


def parse_markers(text: str) -> tuple[str, bool, bool]:
    """Strip [END] / [GIVE UP] and report which were present."""
    found = {m.upper() for m in _MARKERS.findall(text)}
    return _MARKERS.sub("", text).strip(), "END" in found, "GIVE UP" in found


class TextCaller:
    def __init__(self, llm: LLMClient, scenario: Scenario, restaurant: str) -> None:
        self.llm = llm
        self.instructions = caller_prompt(scenario, restaurant)
        self.interrupts = [b for b in scenario.behaviors if b.action == "interrupt"]
        # Audio-only behaviors have no meaning in text; the report lists them as skipped.
        self.skipped_behaviors = [b for b in scenario.behaviors if b.action != "interrupt"]
        self.history: list[Message] = []  # from the caller's side: agent = user, caller = assistant
        self.turn = 0
        self.usage = Usage()
        self._fired: set[int] = set()
        self.said_scripted: list[str] = []  # scripted lines already spoken, kept in the prompt

    async def respond(self, agent_text: str, phase: Phase = None) -> CallerTurn:
        self.turn += 1
        self.history.append(UserMessage(agent_text))
        line = self._scripted_line(phase)
        if line is not None:
            self.history.append(AssistantMessage(line))
            self.said_scripted.append(line)
            return CallerTurn(line, ended=False, gave_up=False, scripted=True, usage=Usage())

        reply = await self.llm.complete(self.current_instructions(), self.history, [])
        self.usage += reply.usage
        text, ended, gave_up = parse_markers(reply.text)
        if text:
            self.history.append(AssistantMessage(text))
        return CallerTurn(text, ended=ended, gave_up=gave_up, scripted=False, usage=reply.usage)

    def current_instructions(self) -> str:
        """The prompt, plus any scripted lines already said.

        A line in the history alone wasn't enough: the caller said "make that a
        cappuccino instead", then later insisted on the latte from its goal.
        """
        if not self.said_scripted:
            return self.instructions
        lines = "\n".join(f'- "{line}"' for line in self.said_scripted)
        return f"{self.instructions}\n\n## Lines you already said in this call\n\n{lines}"

    def _scripted_line(self, phase: Phase) -> str | None:
        for i, behavior in enumerate(self.interrupts):
            if i not in self._fired and self._triggered(behavior, phase):
                self._fired.add(i)
                return behavior.say
        return None

    def _triggered(self, behavior: Behavior, phase: Phase) -> bool:
        trigger = behavior.trigger
        if trigger.turn is not None:
            return trigger.turn == self.turn
        if trigger.phase == "readback":
            return phase == "readback"
        return trigger.phase == "any_agent_speech"  # in text, the first chance to reply
