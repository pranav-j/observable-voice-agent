"""The core (menu, order, tools, prompts) must never import LiveKit or the voice worker."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "voice_order"
CORE_PACKAGES = ("menu", "order", "tools", "prompts")
FORBIDDEN = ("livekit", "voice_order.agent")


def imported_modules(source: str, package: str) -> set[str]:
    """Absolute names of everything `source` imports; relative ones resolve against `package`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            found.add(target)
            found.update(f"{target}.{alias.name}" for alias in node.names)
    return found


def is_forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f + ".") for f in FORBIDDEN)


def package_of(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    return ".".join(rel.parts[:-1])


def core_files() -> list[Path]:
    return sorted(p for pkg in CORE_PACKAGES for p in (SRC / pkg).rglob("*.py"))


@pytest.mark.parametrize("path", core_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_core_module_has_no_livekit_imports(path: Path) -> None:
    bad = sorted(m for m in imported_modules(path.read_text(), package_of(path)) if is_forbidden(m))
    assert not bad, f"{path.relative_to(SRC)} imports {bad}"


@pytest.mark.parametrize(
    "source",
    [
        "import livekit",
        "import livekit.agents as agents",
        "from livekit.agents import Agent",
        "from voice_order.agent import worker",
        "from ..agent import worker",
        "from .. import agent",
    ],
)
def test_checker_catches_violations(source: str) -> None:
    modules = imported_modules(source, package="voice_order.tools")
    assert any(is_forbidden(m) for m in modules)


@pytest.mark.parametrize(
    "source",
    [
        "import json",
        "from pydantic import BaseModel",
        "from ..order import models",
        "from . import x",
    ],
)
def test_checker_allows_clean_imports(source: str) -> None:
    modules = imported_modules(source, package="voice_order.tools")
    assert not any(is_forbidden(m) for m in modules)
