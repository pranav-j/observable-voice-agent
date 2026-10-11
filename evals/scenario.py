"""Scenario files (evals/scenarios/*.yaml): who calls, what they want, what should happen."""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from voice_order.menu.models import Menu
from voice_order.order.models import MAX_QUANTITY, OrderStatus

SCENARIO_DIR = Path(__file__).parent / "scenarios"

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
# Scenario phone numbers must be obviously fake: 90000 and five more digits. Keep the
# second group varied; a long run of one digit is hard for speech recognition, so only
# the scenario that tests that on purpose uses one.
FakePhone = Annotated[str, StringConstraints(pattern=r"^90000\d{5}$")]
Style = Literal["brisk", "chatty", "hesitant", "confused", "adversarial"]


class _Strict(BaseModel):
    # A typo in a YAML key is an error, not a silently ignored field.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Noise(_Strict):
    clip: str
    snr_db: float


class Persona(_Strict):
    name: str
    style: Style
    voice: str | None = None  # audio mode only
    noise: Noise | None = None  # audio mode only


class Customer(_Strict):
    name: str
    phone: FakePhone


class Trigger(_Strict):
    # "phone": the caller's utterance that gives the phone number (pauses only).
    phase: Literal["readback", "any_agent_speech", "phone"] | None = None
    turn: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.phase is None) == (self.turn is None):
            raise ValueError("a trigger needs exactly one of phase or turn")
        return self


class Behavior(_Strict):
    """Scripted caller behavior. Timing only matters in audio mode; text mode uses `say`."""

    trigger: Trigger
    action: Literal["interrupt", "pause_mid_utterance"]
    after_ms: Annotated[int, Field(ge=0)] | None = None
    pause_ms: Annotated[int, Field(gt=0)] | None = None
    say: str | None = None

    @model_validator(mode="after")
    def _fields_for_action(self) -> Self:
        if self.action == "interrupt" and (self.after_ms is None or not self.say):
            raise ValueError("interrupt needs after_ms and say")
        if self.action == "pause_mid_utterance" and self.pause_ms is None:
            raise ValueError("pause_mid_utterance needs pause_ms")
        if self.action == "interrupt" and self.trigger.phase == "phone":
            raise ValueError("the phone phase is for pauses, not interruptions")
        return self


class ExpectedItem(_Strict):
    item: str
    size: str | None = None
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)] = 1
    modifiers: list[str] = []


class ExpectedOrder(_Strict):
    items: list[ExpectedItem]
    customer: Customer | None = None


class Expectation(_Strict):
    status: OrderStatus
    order: ExpectedOrder | None = None  # None: the order's contents are not scored


class Scenario(_Strict):
    id: Slug
    description: str
    tags: list[str] = []
    runs: Annotated[int, Field(ge=1)] = 1
    max_turns: Annotated[int, Field(ge=1)] = 30
    persona: Persona
    goal: str
    customer: Customer
    behaviors: list[Behavior] = []
    expect: Expectation


def load_scenario(path: Path) -> Scenario:
    scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if scenario.id != path.stem:
        raise ValueError(f"{path.name}: id {scenario.id!r} must match the file name")
    return scenario


def load_scenarios(pattern: str = "*", directory: Path = SCENARIO_DIR) -> list[Scenario]:
    """Scenarios whose file name matches `pattern`: one or more comma-separated globs,
    without the .yaml. Each file is loaded once even if several globs match it."""
    paths = {p for glob in pattern.split(",") for p in directory.glob(f"{glob.strip()}.yaml")}
    return [load_scenario(p) for p in sorted(paths)]


def menu_problems(scenario: Scenario, menu: Menu) -> list[str]:
    """Ways the expected order can't exist on this menu. Empty means it's consistent."""
    if scenario.expect.order is None:
        return []
    problems = []
    for expected in scenario.expect.order.items:
        item = menu.item(expected.item)
        if item is None:
            problems.append(f"unknown item {expected.item!r}")
            continue
        sizes = {s.id for s in item.sizes}
        if sizes and expected.size not in sizes:
            problems.append(f"{item.id}: size {expected.size!r} not in {sorted(sizes)}")
        if not sizes and expected.size is not None:
            problems.append(f"{item.id}: has no sizes, got {expected.size!r}")
        modifiers = {m.id for m in item.modifiers}
        for mod in expected.modifiers:
            if mod not in modifiers:
                problems.append(f"{item.id}: unknown modifier {mod!r}")
        if not item.in_stock and scenario.expect.status == "confirmed":
            problems.append(f"{item.id} is out of stock but expected in a confirmed order")
    return problems
