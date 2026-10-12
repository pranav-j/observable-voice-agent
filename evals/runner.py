"""`python -m evals.runner` (or `make eval`): run scenarios and write a report."""

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from openai import AsyncOpenAI
from psycopg_pool import PoolTimeout

from evals.audio.caller import CallerVoice, Hearing
from evals.audio.cost import estimate, past_call_costs
from evals.audio_run import run_audio_scenario
from evals.judge.apply import apply_judges, attach_calibration
from evals.recorded import RECORDED_DIR, load_annotations, score_recorded
from evals.report import report_dir, write_report
from evals.scenario import (
    SCENARIO_DIR,
    Scenario,
    expectation_problems,
    load_scenarios,
    menu_problems,
)
from evals.text_run import RunResult, run_text_scenario
from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu
from voice_order.store.base import InMemoryOrderStore, OrderStore
from voice_order.store.postgres import PostgresOrderStore
from voice_order.textmode.llm import LLMClient
from voice_order.textmode.openai_client import OpenAIClient

LLMFactory = Callable[[], LLMClient]
Play = Callable[[Scenario, int], Awaitable[RunResult]]

# Audio calls run in real time against one local worker, so fewer at once.
DEFAULT_CONCURRENCY = {"text": 4, "audio": 2}


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
    play: Play,
    on_result: Callable[[RunResult], None] = lambda r: None,
) -> list[RunResult]:
    """Every (scenario, run) pair, at most `concurrency` calls at a time."""
    semaphore = asyncio.Semaphore(concurrency)
    jobs = [(s, i) for s in scenarios for i in range(1, (runs or s.runs) + 1)]

    async def one(scenario: Scenario, run: int) -> RunResult:
        async with semaphore:
            result = await play(scenario, run)
        on_result(result)
        return result

    return list(await asyncio.gather(*(one(s, i) for s, i in jobs)))


def text_player(
    *, menu: Menu, store: OrderStore, agent_llm: LLMFactory, caller_llm: LLMFactory
) -> Play:
    def play(scenario: Scenario, run: int) -> Awaitable[RunResult]:
        return run_text_scenario(
            scenario, run, menu=menu, store=store, agent_llm=agent_llm(), caller_llm=caller_llm()
        )

    return play


def audio_player(
    *,
    settings: Settings,
    menu: Menu,
    store: OrderStore,
    caller_llm: LLMFactory,
    hearing: Hearing,
    raw_dir: Path,
    caller_voice: CallerVoice = "openai",
) -> Play:
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    kokoro = load_kokoro(Path(settings.models_dir) / "kokoro") if caller_voice == "kokoro" else None

    def play(scenario: Scenario, run: int) -> Awaitable[RunResult]:
        return run_audio_scenario(
            scenario,
            run,
            settings=settings,
            menu=menu,
            store=store,
            caller_llm=caller_llm(),
            client=client,
            hearing=hearing,
            raw_dir=raw_dir,
            caller_voice=caller_voice,
            kokoro=kokoro,
        )

    return play


def load_kokoro(model_dir: Path) -> Any:
    """One Kokoro for every simulated caller in the run; it takes a second to load."""
    from kokoro_onnx import Kokoro  # heavy import, only for --caller-voice kokoro

    return Kokoro(str(model_dir / "kokoro-v1.0.onnx"), str(model_dir / "voices-v1.0.bin"))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run eval scenarios and write a report.")
    p.add_argument("--mode", choices=["text", "audio", "recorded"], default="text")
    p.add_argument(
        "--scenarios", default="*", help="glob over scenario names (recorded: session ids)"
    )
    p.add_argument("--runs", type=int, help="runs per scenario (default: each scenario's own)")
    p.add_argument("--concurrency", type=int, help="calls at once (default: 4 text, 2 audio)")
    p.add_argument("--memory", action="store_true", help="in-memory store instead of Postgres")
    p.add_argument(
        "--hearing",
        choices=["transcript", "stt"],
        default="transcript",
        help="audio: how the caller understands the agent (timing always comes from audio)",
    )
    p.add_argument("--yes", action="store_true", help="audio: run even if the estimate is high")
    p.add_argument(
        "--caller-voice",
        choices=["openai", "kokoro"],
        default="openai",
        help="audio: the simulated caller's voice (kokoro runs locally; make models first)",
    )
    p.add_argument("--no-judge", action="store_true", help="skip the LLM judges afterwards")
    p.add_argument("--reports-dir", type=Path, default=Path("reports"))
    p.add_argument("--scenario-dir", type=Path, default=SCENARIO_DIR)
    p.add_argument("--recorded-dir", type=Path, default=RECORDED_DIR, help="recorded: annotations")
    return p


async def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    agent_llm: LLMFactory | None = None,
    caller_llm: LLMFactory | None = None,
    judge_llm: LLMClient | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.mode != "text" and args.memory:
        print(
            f"{args.mode.capitalize()} runs read the order the worker saved, so they need "
            "Postgres. Drop --memory and run `make up`.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "recorded":
        return await _recorded(args, settings or get_settings())

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
    total = sum(args.runs or s.runs for s in scenarios)
    if args.mode == "audio" and not _audio_go_ahead(settings, total, yes=args.yes):
        return 2
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
    concurrency = args.concurrency or DEFAULT_CONCURRENCY[args.mode]
    out: Path | None = None
    play: Play
    if args.mode == "audio":
        out = report_dir(args.reports_dir, mode="audio", started_at=started_at)
        play = audio_player(
            settings=settings,
            menu=menu,
            store=store,
            caller_llm=caller_llm,
            hearing=args.hearing,
            raw_dir=out / "raw" / "audio",
            caller_voice=args.caller_voice,
        )
    else:
        play = text_player(menu=menu, store=store, agent_llm=agent_llm, caller_llm=caller_llm)
    print(f"{len(scenarios)} scenarios, {total} runs, concurrency {concurrency}")
    try:
        results = await run_suite(
            scenarios,
            runs=args.runs,
            concurrency=concurrency,
            play=play,
            on_result=lambda r: print(progress_line(r), flush=True),
        )
        out = write_report(
            results,
            mode=args.mode,
            started_at=started_at,
            reports_dir=args.reports_dir,
            out=out,
            concurrency=concurrency,
        )
        judge = judge_llm
        if judge is None and settings.has_openai_key:
            judge = OpenAIClient.from_settings(settings, model=settings.caller_llm_model)
        if judge is not None and not args.no_judge:
            # Before the store closes: the injection check reads the final orders.
            await apply_judges(
                out,
                llm=judge,
                menu=menu,
                store=store,
                recordings_dir=Path(settings.recordings_dir),
                scenario_dir=args.scenario_dir,
            )
            attach_calibration(out)
    finally:
        if pg is not None:
            await pg.close()

    passed = sum(r.score.task_success for r in results)
    print(f"task success {passed}/{len(results)}. Report: {out / 'summary.md'}")
    return 0


async def _recorded(args: argparse.Namespace, settings: Settings) -> int:
    """Score annotated real calls. No LLM calls, so nothing to estimate or confirm."""
    annotations = load_annotations(args.scenarios, directory=args.recorded_dir)
    if not annotations:
        print(
            f"No annotated calls match {args.scenarios!r} in {args.recorded_dir}. "
            "Start one with `make annotate SESSION=<id>`.",
            file=sys.stderr,
        )
        return 2
    menu = load_menu()
    bad = {a.session_id: expectation_problems(a.expect, menu) for a in annotations}
    if any(bad.values()):
        for sid, found in bad.items():
            for problem in found:
                print(f"{sid}: {problem}", file=sys.stderr)
        return 2
    try:
        pg = await PostgresOrderStore.connect(settings.database_url, connect_timeout=3)
    except (PoolTimeout, psycopg.OperationalError):
        print("Can't reach Postgres. Run `make up`.", file=sys.stderr)
        return 2
    started_at = datetime.now(UTC)
    recordings = Path(settings.recordings_dir)
    print(f"{len(annotations)} recorded calls")
    try:
        results = [
            await score_recorded(a, store=pg, recordings_dir=recordings) for a in annotations
        ]
    finally:
        await pg.close()
    for r in results:
        print(progress_line(r))
    out = write_report(
        results, mode="recorded", started_at=started_at, reports_dir=args.reports_dir
    )
    passed = sum(r.score.task_success for r in results)
    print(f"task success {passed}/{len(results)}. Report: {out / 'summary.md'}")
    return 0


def _audio_go_ahead(settings: Settings, runs: int, *, yes: bool) -> bool:
    """Print what an audio run is likely to cost; stop unless it's small or --yes."""
    guess = estimate(runs, past_call_costs(Path(settings.recordings_dir)))
    amount = "unknown" if guess.usd is None else f"about ${guess.usd:.2f}"
    print(f"Audio run: {runs} real calls, agent cost {amount} ({guess.basis}).")
    print("The worker must be running: `make worker` in another terminal.")
    if guess.needs_yes(runs) and not yes:
        print("Re-run with --yes to go ahead (make eval ... ARGS=--yes).", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
