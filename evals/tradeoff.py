"""`python -m evals.tradeoff <out.svg> <report> [<report> ...]`: cut-offs against latency.

One point per report: caller-side response latency p50 across, false cut-off rate up. The
label is the turn-detection setting the worker ran with, from the report's agent config.
Every number on the chart comes from the reports' summary.json.
"""

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

W, H = 640, 360
LEFT, RIGHT, TOP, BOTTOM = 70, 30, 50, 60  # plot margins, px


def point(summary: dict[str, Any]) -> tuple[float, float, int, int]:
    a = summary["audio"]
    return (
        a["response_latency_ms_p50"] / 1000,
        a["false_cutoff_rate"],
        a["false_cutoffs"],
        a["scripted_pauses"],
    )


def label(summary: dict[str, Any]) -> str:
    config = (summary["audio"].get("agent_configs") or [{}])[0]
    detection = config.get("turn_detection", "semantic")
    return f"{detection}, {config.get('eou_silence_ms', '?')} ms"


def render(rows: list[tuple[str, dict[str, Any]]]) -> str:
    points = [(name, *point(s)) for name, s in rows]
    xs = [p[1] for p in points]
    x0, x1 = min(xs) - 0.5, max(xs) + 0.5
    y1 = max(0.5, max(p[2] for p in points) + 0.1)

    def sx(x: float) -> float:
        return LEFT + (x - x0) / (x1 - x0) * (W - LEFT - RIGHT)

    def sy(y: float) -> float:
        return H - BOTTOM - y / y1 * (H - TOP - BOTTOM)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        '<text x="12" y="22" font-size="14" font-weight="bold" fill="#222">'
        "Turn detection: cut-offs against reply speed</text>",
        f'<line x1="{LEFT}" y1="{H - BOTTOM}" x2="{W - RIGHT}" y2="{H - BOTTOM}" stroke="#888"/>',
        f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{H - BOTTOM}" stroke="#888"/>',
        f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{H - 18}" text-anchor="middle" fill="#222">'
        "Response latency p50, caller side (s)</text>",
        f'<text x="18" y="{(TOP + H - BOTTOM) / 2:.0f}" text-anchor="middle" fill="#222" '
        f'transform="rotate(-90 18 {(TOP + H - BOTTOM) / 2:.0f})">False cut-off rate</text>',
    ]
    tick = 0.5
    t = round(x0 / tick) * tick
    while t <= x1:
        if t >= x0:
            out.append(
                f'<text x="{sx(t):.1f}" y="{H - BOTTOM + 16}" text-anchor="middle" '
                f'fill="#555">{t:.1f}</text>'
            )
        t += tick
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        if frac <= y1:
            out.append(
                f'<text x="{LEFT - 8}" y="{sy(frac) + 4:.1f}" text-anchor="end" '
                f'fill="#555">{frac:.2f}</text>'
            )
    placed: list[tuple[float, float, float]] = []  # label boxes so far: x, y, width
    for name, x, y, cut, pauses in sorted(points, key=lambda p: p[1]):
        text = f"{name} ({cut}/{pauses})"
        lx, ly, width = sx(x) + 8, sy(y) - 8, 7.0 * len(text)  # about 7 px per character
        while any(abs(ly - py) < 16 and lx < px + pw and px < lx + width for px, py, pw in placed):
            ly -= 18  # stack upward until it clears the labels already drawn
        placed.append((lx, ly, width))
        out.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" fill="#4c78a8"/>')
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#222">{escape(text)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: python -m evals.tradeoff <out.svg> <report> [<report> ...]", file=sys.stderr)
        return 2
    out, reports = Path(args[0]), [Path(r) for r in args[1:]]
    rows = []
    for report in reports:
        summary = json.loads((report / "summary.json").read_text())
        rows.append((label(summary), summary))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
