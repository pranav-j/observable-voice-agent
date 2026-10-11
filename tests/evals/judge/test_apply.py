"""The judge pass over a finished report, calibration, and the judged report section."""

import json
from datetime import UTC, datetime
from pathlib import Path

from evals.judge.apply import apply_judges, expected_total
from evals.judge.calibration import (
    calibrate,
    labels_document,
    load_calibration,
    read_labels,
    sample_cases,
)
from evals.judge.cases import ErrorCase
from evals.report import render_markdown, summarize, write_report
from evals.scenario import load_scenarios
from evals.scoring.order import OrderScore
from evals.text_run import RunResult, TranscriptEntry

from tests.textmode.fakes import ScriptedLLM, reply
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.base import InMemoryOrderStore
from voice_order.textmode.llm import Usage

STARTED = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
SCORE = OrderScore(
    status="confirmed",
    expected_status="confirmed",
    exact_match=True,
    field_accuracy=1.0,
    task_success=True,
    escalated=False,
    expected_escalation=False,
    mismatches=(),
)


def run(scenario_id: str, tags: list[str], transcript: list[TranscriptEntry]) -> RunResult:
    return RunResult(
        scenario_id=scenario_id,
        tags=tags,
        run=1,
        session_id=f"eval-{scenario_id}-r1",
        end_reason="caller_ended",
        turns=3,
        duration_s=1.0,
        score=SCORE,
        agent_usage=Usage(),
        caller_usage=Usage(),
        tool_limit_hits=0,
        skipped_behaviors=[],
        agent_model="m",
        caller_model="m",
        agent_prompt_version="v1",
        caller_prompt_version="v3",
        transcript=transcript,
    )


PIZZA = [
    TranscriptEntry(speaker="caller", text="A pizza"),
    TranscriptEntry(
        speaker="agent",
        text="Sorry, no pizza here.",
        tool_calls=[{"name": "add_item", "arguments": {}, "ok": False, "error": "UNKNOWN_ITEM"}],
    ),
]


def test_expected_total_is_priced_from_the_menu(menu: Menu) -> None:
    (scenario,) = load_scenarios("injection_discount_demand")
    biryani = menu.item("chicken_biryani")
    assert biryani is not None
    full = next(s.price_paise for s in biryani.sizes if s.id == "full")
    assert expected_total(scenario.expect, menu) == full


async def test_apply_judges_a_text_report(tmp_path: Path, menu: Menu) -> None:
    (injection,) = load_scenarios("injection_discount_demand")
    results = [
        run("unknown_item_pizza", ["unknown_item"], PIZZA),
        run("injection_discount_demand", ["injection", "discount"], []),
    ]
    out = write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
    final = state.new_order("eval-injection_discount_demand-r1")
    for item in injection.expect.order.items if injection.expect.order else []:
        final = state.add_line(final, menu, item.item, item.quantity, item.size, item.modifiers)
    store = InMemoryOrderStore()
    await store.save(final)
    llm = ScriptedLLM(  # runs are judged in report order: by scenario id
        reply('{"agreed_to_discount": false, "reason": "refused"}'),
        reply('{"acknowledged": true, "reason": "said so"}'),
    )
    judged = await apply_judges(
        out, llm=llm, menu=menu, store=store, recordings_dir=tmp_path / "none"
    )
    assert judged[0].judge is not None
    assert judged[0].judge["injection"]["resisted"] is True
    summary = json.loads((out / "summary.json").read_text())
    assert summary["judged"]["error_acknowledgement_rate"] == 1.0
    assert summary["judged"]["injection_resistance_rate"] == 1.0
    assert "## Judged" in (out / "summary.md").read_text()
    rows = [json.loads(line) for line in (out / "judge.jsonl").read_text().splitlines()]
    assert [r["judge"] for r in rows] == ["discount", "error_ack"]
    # results.jsonl now carries the verdict summary, and still loads
    reloaded = [RunResult.model_validate_json(x) for x in (out / "results.jsonl").open()]
    assert reloaded[0].judge == judged[0].judge


async def test_without_the_store_injection_is_unknown(tmp_path: Path, menu: Menu) -> None:
    results = [run("injection_discount_demand", ["injection"], [])]
    out = write_report(results, mode="text", started_at=STARTED, reports_dir=tmp_path)
    llm = ScriptedLLM(reply('{"agreed_to_discount": false, "reason": "refused"}'))
    (judged,) = await apply_judges(out, llm=llm, menu=menu, store=None, recordings_dir=tmp_path)
    assert judged.judge is not None
    assert judged.judge["injection"]["resisted"] is None
    md = render_markdown(summarize([judged], mode="text", started_at=STARTED))
    assert "(0 of 1 runs, 1 unknown)" in md


# --- calibration ------------------------------------------------------------------------


def case(index: int, reply_text: str = "Sorry, no pizza.") -> ErrorCase:
    return ErrorCase(
        session_id="s1",
        index=index,
        tool="add_item",
        arguments={"item_id": "pizza"},
        error="UNKNOWN_ITEM",
        message="",
        reply=reply_text,
    )


def test_sample_is_fixed_and_capped() -> None:
    cases = [case(i) for i in range(50)]
    first = sample_cases(cases, 20)
    assert len(first) == 20
    assert first == sample_cases(cases, 20)
    assert sample_cases(cases[:5], 20) == cases[:5]


def test_sample_spreads_across_error_types() -> None:
    phones = [case(i).model_copy(update={"error": "INVALID_PHONE"}) for i in range(30)]
    sizes = [case(100 + i).model_copy(update={"error": "INVALID_SIZE"}) for i in range(3)]
    chosen = sample_cases(phones + sizes, 10)
    assert sum(c.error == "INVALID_SIZE" for c in chosen) == 3


def test_labels_round_trip_and_skip_unlabeled(tmp_path: Path) -> None:
    path = tmp_path / "labels.yaml"
    path.write_text(labels_document([case(0), case(1)]))
    assert read_labels(path) == []
    path.write_text(path.read_text().replace("acknowledged: null", "acknowledged: true", 1))
    ((labeled, label),) = read_labels(path)
    assert (labeled, label) == (case(0), True)


async def test_calibrate_counts_agreement() -> None:
    llm = ScriptedLLM(
        reply('{"acknowledged": true, "reason": "ok"}'),
        reply('{"acknowledged": true, "reason": "ok"}'),
    )
    result = await calibrate([(case(0), True), (case(1, "Added!"), False)], llm)
    assert (result["agreed"], result["labeled"], result["agreement"]) == (1, 2, 0.5)
    assert result["disagreements"][0]["id"] == "s1#1"


def test_calibration_only_counts_for_its_judge_version(tmp_path: Path) -> None:
    assert load_calibration(tmp_path) is None
    (tmp_path / "result.json").write_text(json.dumps({"version": "v0", "agreed": 1}))
    assert load_calibration(tmp_path) is None
    (tmp_path / "result.json").write_text(
        json.dumps({"version": "v1", "agreed": 19, "labeled": 20, "agreement": 0.95})
    )
    calibration = load_calibration(tmp_path)
    assert calibration is not None
    summary = summarize(
        [run("x", [], []).model_copy(update={"judge": {"error_ack": _ack(2, 2)}})],
        mode="text",
        started_at=STARTED,
    )
    summary["judge_calibration"] = calibration
    assert "19/20 hand labels (95.0%), judge v1" in render_markdown(summary)


def _ack(cases: int, acknowledged: int) -> dict[str, object]:
    return {"version": "v1", "cases": cases, "acknowledged": acknowledged, "unreadable": 0}
