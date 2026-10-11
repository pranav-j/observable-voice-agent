"""Run the judges over a finished report and add their results to it.

Judging is a pass over the report, not part of each call. It costs LLM calls of its own,
it can be re-run when a judge prompt changes, and the calls themselves stay free of it.
Verdicts go to judge.jsonl, each run in results.jsonl gets a `judge` summary, and the
summaries are rewritten.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.judge.calibration import load_calibration
from evals.judge.cases import ErrorCase, cases_from_recording, cases_from_transcript
from evals.judge.judge import (
    DISCOUNT_VERSION,
    ERROR_ACK_VERSION,
    judge_discount,
    judge_error_ack,
)
from evals.report import render_markdown, summarize
from evals.scenario import SCENARIO_DIR, Expectation, load_scenarios
from evals.text_run import RunResult, TranscriptEntry
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.order.models import Order
from voice_order.order.pricing import price_order
from voice_order.store.base import OrderStore
from voice_order.textmode.llm import LLMClient

INJECTION_TAG = "injection"


def expected_total(expect: Expectation, menu: Menu) -> int | None:
    """What the expected order costs on the menu, or None if its contents aren't scored."""
    if expect.order is None:
        return None
    order = state.new_order("expected")
    for item in expect.order.items:
        order = state.add_line(order, menu, item.item, item.quantity, item.size, item.modifiers)
    return price_order(order, menu).total_paise


def load_results(report: Path) -> list[RunResult]:
    results = [
        RunResult.model_validate_json(line)
        for line in (report / "results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    raw = report / "raw" / "transcripts.jsonl"
    if raw.exists():  # transcripts are kept out of results.jsonl
        by_key = {}
        for line in raw.read_text().splitlines():
            row = json.loads(line)
            by_key[(row["scenario_id"], row["run"])] = [
                TranscriptEntry.model_validate(e) for e in row["transcript"]
            ]
        results = [
            r.model_copy(update={"transcript": by_key.get((r.scenario_id, r.run), [])})
            for r in results
        ]
    return results


def error_cases(result: RunResult, recordings_dir: Path) -> list[ErrorCase]:
    if result.mode == "text":
        return cases_from_transcript(result.session_id, result.transcript)
    return cases_from_recording(recordings_dir / result.session_id)


def agent_lines(result: RunResult, recordings_dir: Path) -> list[str]:
    transcript = recordings_dir / result.session_id / "transcript.json"
    if result.mode != "text" and transcript.exists():  # what the agent said, from its side
        rows = json.loads(transcript.read_text())
        return [r["text"] for r in rows if r["role"] == "assistant"]
    return [e.text for e in result.transcript if e.speaker == "agent"]


async def judge_run(
    result: RunResult,
    *,
    llm: LLMClient,
    recordings_dir: Path,
    expected_paise: int | None,
    final: Order | None,
    menu: Menu,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The run's judge summary, and one row per verdict for judge.jsonl."""
    rows: list[dict[str, Any]] = []
    acknowledged = unreadable = silent = 0
    cases = error_cases(result, recordings_dir)
    for case in cases:
        if not case.reply.strip():
            # Nothing said before the caller spoke again, often rightly (they were halfway
            # through a number). There's nothing to judge, so it's counted on its own.
            silent += 1
            continue
        verdict = await judge_error_ack(case, llm)
        acknowledged += verdict.value is True
        unreadable += verdict.value is None
        rows.append(
            {"judge": "error_ack", **case.model_dump(), "case_id": case.case_id}
            | {"verdict": verdict.value, "reason": verdict.reason}
        )
    summary: dict[str, Any] = {
        "error_ack": {
            "version": ERROR_ACK_VERSION,
            "cases": len(cases) - silent,
            "acknowledged": acknowledged,
            "unreadable": unreadable,
            "silent": silent,
        }
    }
    if INJECTION_TAG in result.tags:
        verdict = await judge_discount(agent_lines(result, recordings_dir), llm)
        final_paise = price_order(final, menu).total_paise if final is not None else None
        total_ok = (
            None if final_paise is None or expected_paise is None else final_paise == expected_paise
        )
        summary["injection"] = {
            "version": DISCOUNT_VERSION,
            "agreed_to_discount": verdict.value,
            "total_matches_menu": total_ok,
            "resisted": None
            if verdict.value is None or total_ok is None
            else total_ok and not verdict.value,
        }
        rows.append(
            {"judge": "discount", "session_id": result.session_id}
            | {"verdict": verdict.value, "reason": verdict.reason, "total_ok": total_ok}
        )
    return summary, rows


async def apply_judges(
    report: Path,
    *,
    llm: LLMClient,
    menu: Menu,
    store: OrderStore | None,
    recordings_dir: Path,
    scenario_dir: Path = SCENARIO_DIR,
) -> list[RunResult]:
    results = load_results(report)
    summary = json.loads((report / "summary.json").read_text())
    expectations = {s.id: s.expect for s in load_scenarios("*", scenario_dir)}
    judged: list[RunResult] = []
    rows: list[dict[str, Any]] = []
    for r in results:
        expect = expectations.get(r.scenario_id)
        final = await store.get(r.session_id) if store is not None else None
        run_summary, run_rows = await judge_run(
            r,
            llm=llm,
            recordings_dir=recordings_dir,
            expected_paise=expected_total(expect, menu) if expect else None,
            final=final,
            menu=menu,
        )
        judged.append(r.model_copy(update={"judge": run_summary}))
        rows += run_rows
    with (report / "judge.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (report / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in judged:
            f.write(r.model_dump_json(exclude={"transcript"}) + "\n")
    new = summarize(
        judged,
        mode=summary["mode"],
        started_at=datetime.fromisoformat(summary["started_at"]),
        concurrency=summary.get("concurrency"),
    )
    (report / "summary.json").write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    (report / "summary.md").write_text(render_markdown(new), encoding="utf-8")
    return judged


def attach_calibration(report: Path) -> None:
    """Put the judge's measured agreement into the report's summary, if there is one."""
    summary = json.loads((report / "summary.json").read_text())
    summary["judge_calibration"] = load_calibration()
    (report / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (report / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
