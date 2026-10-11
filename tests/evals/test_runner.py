"""The eval runner CLI, end to end, with scripted LLMs instead of OpenAI."""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from evals.runner import main, run_suite, text_player
from evals.scenario import load_scenarios

from tests.evals.scripts import HAPPY_AGENT, HAPPY_CALLER
from tests.textmode.fakes import ScriptedLLM, reply
from voice_order.config import Settings
from voice_order.menu.models import Menu
from voice_order.store.base import InMemoryOrderStore
from voice_order.textmode.llm import LLMReply, Message, ToolSpec

HAPPY_ARGS = ["--scenarios", "happy_path_single_coffee", "--memory"]


def happy_agent() -> ScriptedLLM:
    return ScriptedLLM(*HAPPY_AGENT)


def happy_caller() -> ScriptedLLM:
    return ScriptedLLM(*HAPPY_CALLER)


def no_key() -> Settings:
    return Settings(_env_file=None, openai_api_key="")


def read_report(reports_dir: Path) -> tuple[dict[str, Any], bool]:
    """Sync on purpose: blocking file reads don't belong inside async tests."""
    (report,) = reports_dir.iterdir()
    return json.loads((report / "summary.json").read_text()), (report / "summary.md").exists()


async def test_cli_runs_scenarios_and_writes_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await main(
        [*HAPPY_ARGS, "--runs", "2", "--reports-dir", str(tmp_path)],
        settings=no_key(),
        agent_llm=happy_agent,
        caller_llm=happy_caller,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "1 scenarios, 2 runs, concurrency 4" in out
    assert out.count("PASS happy_path_single_coffee") == 2
    assert "task success 2/2." in out
    summary, has_markdown = read_report(tmp_path)
    assert summary["overall"]["task_successes"] == 2
    assert has_markdown
    assert summary["judged"] is None  # no API key and no judge given: judging is skipped


async def test_judges_run_after_the_suite(tmp_path: Path) -> None:
    code = await main(
        [*HAPPY_ARGS, "--runs", "1", "--reports-dir", str(tmp_path)],
        settings=no_key(),
        agent_llm=happy_agent,
        caller_llm=happy_caller,
        judge_llm=ScriptedLLM(),  # the happy path has no tool errors to judge
    )
    assert code == 0
    summary, _ = read_report(tmp_path)
    assert summary["judged"]["error_ack_cases"] == 0


async def test_each_scenario_uses_its_own_runs_by_default(menu: Menu) -> None:
    scenarios = load_scenarios("happy_path_single_coffee")
    assert scenarios[0].runs == 3
    play = text_player(
        menu=menu, store=InMemoryOrderStore(), agent_llm=happy_agent, caller_llm=happy_caller
    )
    results = await run_suite(scenarios, runs=None, concurrency=2, play=play)
    assert sorted(r.run for r in results) == [1, 2, 3]


class ProbeLLM:
    """A caller that ends the call at once, while tracking how many calls overlap."""

    model = "probe"
    active = 0
    peak = 0

    async def complete(
        self, instructions: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMReply:
        ProbeLLM.active += 1
        ProbeLLM.peak = max(ProbeLLM.peak, ProbeLLM.active)
        await asyncio.sleep(0.01)
        ProbeLLM.active -= 1
        return reply("[END]")


async def test_concurrency_is_capped(menu: Menu) -> None:
    ProbeLLM.active = ProbeLLM.peak = 0
    play = text_player(
        menu=menu, store=InMemoryOrderStore(), agent_llm=ScriptedLLM, caller_llm=ProbeLLM
    )
    results = await run_suite(
        load_scenarios("happy_path_single_coffee"), runs=6, concurrency=2, play=play
    )
    assert len(results) == 6
    assert ProbeLLM.peak == 2


# --- failing fast, before any money is spent -----------------------------------------------


async def test_recorded_mode_needs_annotations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await main(["--mode", "recorded", "--recorded-dir", str(tmp_path)]) == 2
    assert "make annotate" in capsys.readouterr().err


async def test_recorded_mode_needs_postgres(capsys: pytest.CaptureFixture[str]) -> None:
    assert await main(["--mode", "recorded", "--memory"]) == 2
    assert "need Postgres" in capsys.readouterr().err


async def test_audio_needs_postgres(capsys: pytest.CaptureFixture[str]) -> None:
    assert await main(["--mode", "audio", *HAPPY_ARGS]) == 2
    assert "need Postgres" in capsys.readouterr().err


def _past_audio_calls(recordings: Path, cost: float, count: int) -> None:
    """Sync on purpose, like read_report."""
    for i in range(count):
        folder = recordings / f"audio-x-r{i}"
        folder.mkdir(parents=True)
        (folder / "usage.json").write_text(json.dumps({"total_cost_usd": cost}))


async def test_expensive_audio_runs_need_yes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _past_audio_calls(tmp_path, cost=0.50, count=3)
    settings = Settings(_env_file=None, recordings_dir=str(tmp_path))
    args = ["--mode", "audio", "--scenarios", "happy_path_single_coffee", "--runs", "3"]
    assert await main(args, settings=settings) == 2
    captured = capsys.readouterr()
    assert "Audio run: 3 real calls, agent cost about $1.50" in captured.out
    assert "--yes" in captured.err


async def test_no_matching_scenarios(capsys: pytest.CaptureFixture[str]) -> None:
    assert await main(["--scenarios", "nothing_matches_*"]) == 2
    assert "No scenarios match" in capsys.readouterr().err


async def test_scenarios_that_contradict_the_menu(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad_pizza.yaml").write_text(
        "id: bad_pizza\ndescription: d\npersona: {name: A, style: brisk}\ngoal: pizza\n"
        "customer: {name: A, phone: '9000000001'}\n"
        "expect: {status: confirmed, order: {items: [{item: pizza}]}}\n"
    )
    assert await main(["--scenario-dir", str(tmp_path)]) == 2
    assert "bad_pizza: unknown item 'pizza'" in capsys.readouterr().err


async def test_missing_api_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert await main(HAPPY_ARGS, settings=no_key()) == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


async def test_unreachable_postgres(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, database_url="postgresql://x:y@127.0.0.1:1/none")
    code = await main(
        ["--scenarios", "happy_path_single_coffee"],
        settings=settings,
        agent_llm=happy_agent,
        caller_llm=happy_caller,
    )
    assert code == 2
    assert "Can't reach Postgres" in capsys.readouterr().err
