"""`python -m evals.waterfall <out.svg> <report> [<report> ...]`: a latency waterfall.

One row per report, built from the agent's p50 stage timings: end of turn, then LLM
steps and tools, then text-to-speech up to the first audio. A tick marks the caller-side
p50, measured from the audio the caller received, which also includes the network and
playback. Every number on the chart comes from the reports' summary.json.
"""

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

ROW, LEFT, SCALE = 54, 190, 80  # px; SCALE px per second
COLORS = {"end of turn": "#8e9aaf", "LLM + tools": "#4c78a8", "first audio": "#f58518"}


def stages(summary: dict[str, Any]) -> list[tuple[str, float]]:
    t = summary["audio"]["agent_timing_p50_s"]
    eou, tts, e2e = t["end_of_turn_delay"], t["tts_node_ttfb"], t["e2e_latency"]
    return [("end of turn", eou), ("LLM + tools", max(e2e - eou - tts, 0.0)), ("first audio", tts)]


def render(rows: list[tuple[str, dict[str, Any]]]) -> str:
    height = 70 + ROW * len(rows) + 40
    longest = max(
        max(s["audio"]["response_latency_ms_p50"] / 1000, sum(v for _, v in stages(s)))
        for _, s in rows
    )
    width = int(LEFT + longest * SCALE + 170)  # room for the caller-side label
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        'font-family="Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="12" y="22" font-size="14" font-weight="bold" fill="#222">'
        "Where a reply's time goes (p50)</text>",
        '<text x="12" y="40" fill="#555">Bars: the agent\'s own stage timings. '
        "Tick: when the caller heard the reply start.</text>",
    ]
    for i, (label, summary) in enumerate(rows):
        y = 60 + i * ROW
        out.append(f'<text x="12" y="{y + 20}" fill="#222">{escape(label)}</text>')
        x = float(LEFT)
        for name, seconds in stages(summary):
            w = seconds * SCALE
            out.append(
                f'<rect x="{x:.1f}" y="{y + 6}" width="{w:.1f}" height="22" fill="{COLORS[name]}"/>'
            )
            if w > 34:
                out.append(
                    f'<text x="{x + w / 2:.1f}" y="{y + 21}" fill="#fff" '
                    f'text-anchor="middle">{seconds:.2f}s</text>'
                )
            x += w
        caller = summary["audio"]["response_latency_ms_p50"] / 1000
        cx = LEFT + caller * SCALE
        out.append(f'<line x1="{cx:.1f}" y1="{y + 2}" x2="{cx:.1f}" y2="{y + 32}" stroke="#222"/>')
        out.append(
            f'<text x="{cx + 4:.1f}" y="{y + 44}" fill="#222">caller hears it: {caller:.2f}s</text>'
        )
    ly = 60 + ROW * len(rows) + 14
    x = float(LEFT)
    for name, color in COLORS.items():
        out.append(f'<rect x="{x:.0f}" y="{ly}" width="12" height="12" fill="{color}"/>')
        out.append(f'<text x="{x + 16:.0f}" y="{ly + 10}" fill="#222">{name}</text>')
        x += 120
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: python -m evals.waterfall <out.svg> <report> [<report> ...]", file=sys.stderr)
        return 2
    out, reports = Path(args[0]), [Path(r) for r in args[1:]]
    rows = []
    for report in reports:
        summary = json.loads((report / "summary.json").read_text())
        # A call that errored before the worker joined has no config: skip those.
        configs = [c for c in summary["audio"].get("agent_configs") or [] if c] or [{}]
        speech = "local speech" if configs[0].get("stt_provider") == "whisper" else "hosted speech"
        rows.append((f"{speech} ({report.name[:8]})", summary))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
