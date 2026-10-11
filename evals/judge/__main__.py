"""`python -m evals.judge apply|sample|calibrate` (or the make judge targets).

apply <report>      run the judges over a finished report and rewrite its summary
sample <report>     write 20 of its error cases to calibration/labels.yaml for hand labels
calibrate           compare the judge with the hand labels and record the agreement
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import psycopg
from psycopg_pool import PoolTimeout

from evals.judge.apply import apply_judges, attach_calibration, error_cases, load_results
from evals.judge.calibration import (
    CALIBRATION_DIR,
    calibrate,
    labels_document,
    read_labels,
    sample_cases,
)
from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.store.postgres import PostgresOrderStore
from voice_order.textmode.llm import LLMClient
from voice_order.textmode.openai_client import OpenAIClient


def _judge_llm(settings: Settings, model: str | None) -> LLMClient:
    return OpenAIClient.from_settings(settings, model=model or settings.caller_llm_model)


async def _apply(report: Path, settings: Settings, model: str | None) -> int:
    try:
        store: PostgresOrderStore | None = await PostgresOrderStore.connect(
            settings.database_url, connect_timeout=3
        )
    except (PoolTimeout, psycopg.OperationalError):
        print("Postgres isn't reachable: injection totals will be unknown.", file=sys.stderr)
        store = None
    try:
        judged = await apply_judges(
            report,
            llm=_judge_llm(settings, model),
            menu=load_menu(),
            store=store,
            recordings_dir=Path(settings.recordings_dir),
        )
    finally:
        if store is not None:
            await store.close()
    attach_calibration(report)
    cases = sum((r.judge or {}).get("error_ack", {}).get("cases", 0) for r in judged)
    print(f"Judged {len(judged)} runs, {cases} tool errors. Report: {report / 'summary.md'}")
    return 0


def _sample(report: Path, settings: Settings, n: int, force: bool) -> int:
    out = CALIBRATION_DIR / "labels.yaml"
    if out.exists() and not force:
        print(f"{out} exists. Pass --force to replace it (labels would be lost).", file=sys.stderr)
        return 2
    recordings = Path(settings.recordings_dir)
    cases = [c for r in load_results(report) for c in error_cases(r, recordings)]
    if not cases:
        print("That report has no tool errors to sample.", file=sys.stderr)
        return 2
    chosen = sample_cases(cases, n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(labels_document(chosen), encoding="utf-8")
    print(f"Wrote {len(chosen)} cases to {out}. Label them, then run make judge-calibrate.")
    return 0


async def _calibrate(settings: Settings, model: str | None) -> int:
    labels = CALIBRATION_DIR / "labels.yaml"
    labeled = read_labels(labels) if labels.exists() else []
    if not labeled:
        print(f"No labeled cases in {labels}. Run make judge-sample first.", file=sys.stderr)
        return 2
    result = await calibrate(labeled, _judge_llm(settings, model))
    (CALIBRATION_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Judge agrees with {result['agreed']}/{result['labeled']} hand labels.")
    return 0


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.judge")
    p.add_argument("--judge-model", help="default: CALLER_LLM_MODEL")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("apply").add_argument("report", type=Path)
    sample = sub.add_parser("sample")
    sample.add_argument("report", type=Path)
    sample.add_argument("--n", type=int, default=20)
    sample.add_argument("--force", action="store_true")
    sub.add_parser("calibrate")
    args = p.parse_args(argv)
    settings = get_settings()
    if args.command != "sample" and not settings.has_openai_key:
        print("OPENAI_API_KEY is not set. Add it to .env.", file=sys.stderr)
        return 2
    if args.command == "apply":
        return await _apply(args.report, settings, args.judge_model)
    if args.command == "sample":
        return _sample(args.report, settings, args.n, args.force)
    return await _calibrate(settings, args.judge_model)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
