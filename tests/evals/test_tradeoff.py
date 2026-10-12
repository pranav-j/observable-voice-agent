"""The turn-detection chart: split sentences against the agent's end-of-turn delay."""

import json
from pathlib import Path
from typing import Any

from evals.tradeoff import label, main, point, render


def summary(p50: float, p95: float, splits: int, detection: str, eou: int) -> dict[str, Any]:
    return {
        "audio": {
            "agent_timing_p50_s": {"end_of_turn_delay": p50},
            "agent_timing_p95_s": {"end_of_turn_delay": p95},
            "turn_ends_in_pauses": splits,
            "turn_end_pauses_measured": 9,
            "turn_end_in_pause_rate": splits / 9,
            "agent_configs": [{"turn_detection": detection, "eou_silence_ms": eou}],
        }
    }


def test_label_names_the_turn_setting() -> None:
    assert label(summary(0.9, 1.1, 9, "vad", 300)) == "vad, 300 ms"
    assert label({"audio": {"agent_configs": [{"eou_silence_ms": 500}]}}) == "semantic, 500 ms"


def test_point_reads_delay_and_splits() -> None:
    assert point(summary(0.95, 2.5, 0, "semantic", 500)) == (0.95, 2.5, 0.0, 0, 9)


def test_chart_shows_each_configuration_with_its_counts() -> None:
    rows = [
        ("vad, 300 ms", summary(0.91, 1.15, 9, "vad", 300)),
        ("semantic, 500 ms", summary(0.95, 2.5, 0, "semantic", 500)),
    ]
    svg = render(rows)
    assert svg.startswith("<svg")
    assert svg.count("<circle") == 2
    assert "vad, 300 ms (9/9)" in svg
    assert "semantic, 500 ms (0/9)" in svg


def test_labels_of_nearby_points_dont_overlap() -> None:
    rows = [("a", summary(0.90, 1.1, 9, "vad", 300)), ("b", summary(0.91, 1.1, 9, "vad", 600))]
    ys = [
        float(line.split('y="')[1].split('"')[0])
        for line in render(rows).splitlines()
        if "(9/9)</text>" in line
    ]
    assert len(ys) == 2
    assert abs(ys[0] - ys[1]) >= 16


def test_cli_writes_the_svg(tmp_path: Path) -> None:
    report = tmp_path / "r"
    report.mkdir()
    (report / "summary.json").write_text(json.dumps(summary(1.5, 1.5, 5, "vad", 1500)))
    out = tmp_path / "chart.svg"
    assert main([str(out), str(report)]) == 0
    assert "vad, 1500 ms (5/9)" in out.read_text()
