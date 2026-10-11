"""Versioned prompt files.

Any wording change gets a new version file (agent_system.v2.md, ...), so eval runs
record exactly which prompt they used and can be compared.
"""

from dataclasses import dataclass
from importlib import resources
from string import Template

AGENT_SYSTEM_VERSION = "v1"
GREETING_VERSION = "v1"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


def load_prompt(name: str, version: str, **values: str) -> Prompt:
    """Read `<name>.<version>.md` and fill in `$placeholders`.

    Raises FileNotFoundError for an unknown version and KeyError for a missing value.
    """
    raw = resources.files(__package__).joinpath(f"{name}.{version}.md").read_text("utf-8")
    text = Template(raw).substitute(values).strip()
    return Prompt(name=name, version=version, text=text)


def agent_system_prompt(restaurant: str) -> Prompt:
    return load_prompt("agent_system", AGENT_SYSTEM_VERSION, restaurant=restaurant)


def greeting_prompt(restaurant: str) -> Prompt:
    """The fixed first line of every call, spoken before the model is involved."""
    return load_prompt("greeting", GREETING_VERSION, restaurant=restaurant)
