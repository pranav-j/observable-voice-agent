"""The turn-detection chart: false cut-offs against response latency."""

import json
from pathlib import Path
from typing import Any

from evals.tradeoff import label, main, render


def summary(latency_ms: float, cutoffs: int, detection: str, eou: int) -> dict[str, Any]:
    return {
        "audio": {
            "response_latency_ms_p50": latency_ms,
            "false_cutoffs": cutoffs,
            "scripted_pauses": 9,
            "false_cutoff_rate": cutoffs / 9,
            "agent_configs": [{"turn_detection": detection, "eou_silence_ms": eou}],
        }
    }


def test_label_names_the_turn_setting() -> None:
    assert label(summary(4000, 0, "vad", 300)) == "vad, 300 ms"
    assert label({"audio": {"agent_configs": [{"eou_silence_ms": 500}]}}) == "semantic, 500 ms"


def test_chart_shows_each_configuration_with_its_counts() -> None:
    rows = [
        ("vad, 300 ms", summary(4100, 3, "vad", 300)),
        ("vad, 1500 ms", summary(5900, 0, "vad", 1500)),
    ]
    svg = render(rows)
    assert svg.startswith("<svg")
    assert svg.count("<circle") == 2
    assert "vad, 300 ms (3/9)" in svg
    assert "vad, 1500 ms (0/9)" in svg


def test_cli_writes_the_svg(tmp_path: Path) -> None:
    report = tmp_path / "r"
    report.mkdir()
    (report / "summary.json").write_text(json.dumps(summary(4800, 1, "semantic", 500)))
    out = tmp_path / "chart.svg"
    assert main([str(out), str(report)]) == 0
    assert "semantic, 500 ms (1/9)" in out.read_text()


def test_labels_of_nearby_points_dont_overlap() -> None:
    rows = [("a", summary(4100, 0, "vad", 300)), ("b", summary(4150, 0, "vad", 600))]
    ys = [
        float(line.split('y="')[1].split('"')[0])
        for line in render(rows).splitlines()
        if "(0/9)</text>" in line
    ]
    assert len(ys) == 2
    assert abs(ys[0] - ys[1]) >= 16
