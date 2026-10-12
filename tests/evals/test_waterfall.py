"""The latency waterfall chart, from report summaries."""

import json
import re
from pathlib import Path
from typing import Any

from evals.waterfall import main, render, stages


def summary(eou: float, tts: float, e2e: float, caller_ms: float) -> dict[str, Any]:
    timing = {"end_of_turn_delay": eou, "tts_node_ttfb": tts, "e2e_latency": e2e}
    return {"audio": {"agent_timing_p50_s": timing, "response_latency_ms_p50": caller_ms}}


def test_stages_split_the_agents_time() -> None:
    assert stages(summary(0.5, 1.0, 5.0, 6000)) == [
        ("end of turn", 0.5),
        ("LLM + tools", 3.5),
        ("first audio", 1.0),
    ]


def test_chart_shows_every_number() -> None:
    svg = render([("hosted speech", summary(0.58, 1.10, 5.14, 6756))])
    assert svg.startswith("<svg")
    for label in ("0.58s", "3.46s", "1.10s", "caller hears it: 6.76s"):
        assert label in svg


def test_cli_writes_the_svg(tmp_path: Path) -> None:
    report = tmp_path / "20261012-000000-audio"
    report.mkdir()
    (report / "summary.json").write_text(json.dumps(summary(0.9, 0.7, 4.8, 4885)))
    out = tmp_path / "chart.svg"
    assert main([str(out), str(report)]) == 0
    assert "hosted speech (20261012)" in out.read_text()


def test_chart_is_wide_enough_for_the_slowest_caller_label() -> None:
    svg = render([("slow", summary(0.5, 1.0, 5.0, 9000)), ("fast", summary(0.5, 0.5, 3.0, 4000))])
    width = int(re.search(r'width="(\d+)"', svg).group(1))  # type: ignore[union-attr]
    label_x = float(re.search(r'x="([\d.]+)"[^>]*>caller hears it: 9.00s', svg).group(1))  # type: ignore[union-attr]
    assert label_x + 140 <= width  # about 140 px for "caller hears it: 9.00s" at 12 px
