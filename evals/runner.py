"""`python -m evals.runner` (or `make eval`): run scenarios and write a report."""

import argparse
import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg_pool import PoolTimeout

from evals.report import write_report
from evals.scenario import SCENARIO_DIR, Scenario, load_scenarios, menu_problems
from evals.text_run import RunResult, run_text_scenario
from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu
from voice_order.store.base import InMemoryOrderStore, OrderStore
from voice_order.store.postgres import PostgresOrderStore
from voice_order.textmode.llm import LLMClient
from voice_order.textmode.openai_client import OpenAIClient

LLMFactory = Callable[[], LLMClient]


def progress_line(r: RunResult) -> str:
    verdict = "PASS" if r.score.task_success else "FAIL"
    line = (
        f"{verdict} {r.scenario_id} r{r.run}  {r.end_reason}  {r.turns} turns  {r.duration_s:.1f}s"
    )
    detail = r.error or "; ".join(r.score.mismatches)
    return f"{line}  {detail}" if detail and not r.score.task_success else line


async def run_suite(
    scenarios: list[Scenario],
    *,
    runs: int | None,
    concurrency: int,
    menu: Menu,
    store: OrderStore,
    agent_llm: LLMFactory,
    caller_llm: LLMFactory,
    on_result: Callable[[RunResult], None] = lambda r: None,
) -> list[RunResult]:
    """Every (scenario, run) pair, at most `concurrency` calls at a time."""
    semaphore = asyncio.Semaphore(concurrency)
    jobs = [(s, i) for s in scenarios for i in range(1, (runs or s.runs) + 1)]

    async def one(scenario: Scenario, run: int) -> RunResult:
        async with semaphore:
            result = await run_text_scenario(
                scenario,
                run,
                menu=menu,
                store=store,
                agent_llm=agent_llm(),
                caller_llm=caller_llm(),
            )
        on_result(result)
        return result

    return list(await asyncio.gather(*(one(s, i) for s, i in jobs)))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run eval scenarios and write a report.")
    p.add_argument("--mode", choices=["text", "audio", "recorded"], default="text")
    p.add_argument("--scenarios", default="*", help="glob over scenario file names")
    p.add_argument("--runs", type=int, help="runs per scenario (default: each scenario's own)")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--memory", action="store_true", help="in-memory store instead of Postgres")
    p.add_argument("--reports-dir", type=Path, default=Path("reports"))
    p.add_argument("--scenario-dir", type=Path, default=SCENARIO_DIR)
    return p


async def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    agent_llm: LLMFactory | None = None,
    caller_llm: LLMFactory | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.mode != "text":
        print(f"--mode {args.mode} is not implemented yet.", file=sys.stderr)
        return 2

    scenarios = load_scenarios(args.scenarios, directory=args.scenario_dir)
    if not scenarios:
        print(f"No scenarios match {args.scenarios!r}.", file=sys.stderr)
        return 2
    menu = load_menu()
    problems = {s.id: menu_problems(s, menu) for s in scenarios}
    if any(problems.values()):
        for sid, found in problems.items():
            for problem in found:
                print(f"{sid}: {problem}", file=sys.stderr)
        return 2

    settings = settings or get_settings()
    if agent_llm is None or caller_llm is None:
        if not settings.has_openai_key:
            print("OPENAI_API_KEY is not set. Add it to .env.", file=sys.stderr)
            return 2
        # One client per side, shared by all runs; the SDK pools connections.
        agent_client = OpenAIClient.from_settings(settings)
        caller_client = OpenAIClient.from_settings(settings, model=settings.caller_llm_model)
        agent_llm, caller_llm = (lambda: agent_client), (lambda: caller_client)

    pg: PostgresOrderStore | None = None
    store: OrderStore
    if args.memory:
        store = InMemoryOrderStore()
    else:
        try:
            pg = store = await PostgresOrderStore.connect(settings.database_url, connect_timeout=3)
        except (PoolTimeout, psycopg.OperationalError):
            print("Can't reach Postgres. Run `make up`, or pass --memory.", file=sys.stderr)
            return 2

    started_at = datetime.now(UTC)
    total = sum(args.runs or s.runs for s in scenarios)
    print(f"{len(scenarios)} scenarios, {total} runs, concurrency {args.concurrency}")
    try:
        results = await run_suite(
            scenarios,
            runs=args.runs,
            concurrency=args.concurrency,
            menu=menu,
            store=store,
            agent_llm=agent_llm,
            caller_llm=caller_llm,
            on_result=lambda r: print(progress_line(r), flush=True),
        )
    finally:
        if pg is not None:
            await pg.close()

    out = write_report(results, mode="text", started_at=started_at, reports_dir=args.reports_dir)
    passed = sum(r.score.task_success for r in results)
    print(f"task success {passed}/{len(results)}. Report: {out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
