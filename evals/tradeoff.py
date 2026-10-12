"""`python -m evals.tradeoff <out.svg> <report> [<report> ...]`: split sentences against waiting.

One point per report. Up: the share of scripted mid-sentence pauses where the agent ended
the caller's turn, splitting the sentence. Across: the agent's own end-of-turn delay, a dot
at p50 and a line out to p95. The delay is what a turn-detection setting controls; the
caller-side latency also moves with the LLM's speed from run to run. The label is the
setting the worker ran with, from the report's agent config. Every number comes from the
reports' summary.json.
"""

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

W, H = 680, 380
LEFT, RIGHT, TOP, BOTTOM = 70, 40, 50, 60  # plot margins, px


def point(summary: dict[str, Any]) -> tuple[float, float, float, int, int]:
    """(delay p50 s, delay p95 s, split rate, splits, pauses measured)."""
    a = summary["audio"]
    return (
        a["agent_timing_p50_s"]["end_of_turn_delay"],
        a["agent_timing_p95_s"]["end_of_turn_delay"],
        a["turn_end_in_pause_rate"],
        a["turn_ends_in_pauses"],
        a["turn_end_pauses_measured"],
    )


def label(summary: dict[str, Any]) -> str:
    config = (summary["audio"].get("agent_configs") or [{}])[0]
    detection = config.get("turn_detection", "semantic")
    return f"{detection}, {config.get('eou_silence_ms', '?')} ms"


def render(rows: list[tuple[str, dict[str, Any]]]) -> str:
    points = [(name, *point(s)) for name, s in rows]
    x1 = max(2.0, max(p[2] for p in points) + 1.0)  # room for the label after the line

    def sx(x: float) -> float:
        return LEFT + x / x1 * (W - LEFT - RIGHT)

    def sy(y: float) -> float:
        return H - BOTTOM - y / 1.1 * (H - TOP - BOTTOM)

    mid = (TOP + H - BOTTOM) / 2
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        '<text x="12" y="22" font-size="14" font-weight="bold" fill="#222">'
        "Turn detection: split sentences against waiting</text>",
        '<text x="12" y="38" fill="#555">Dot: end-of-turn delay p50. Line: out to p95.</text>',
        f'<line x1="{LEFT}" y1="{H - BOTTOM}" x2="{W - RIGHT}" y2="{H - BOTTOM}" stroke="#888"/>',
        f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{H - BOTTOM}" stroke="#888"/>',
        f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{H - 18}" text-anchor="middle" fill="#222">'
        "Agent's end-of-turn delay (s)</text>",
        f'<text x="18" y="{mid:.0f}" text-anchor="middle" fill="#222" '
        f'transform="rotate(-90 18 {mid:.0f})">Pauses where the sentence was split</text>',
    ]
    t = 0.0
    while t <= x1 + 1e-9:
        out.append(
            f'<text x="{sx(t):.1f}" y="{H - BOTTOM + 16}" text-anchor="middle" '
            f'fill="#555">{t:.1f}</text>'
        )
        t += 0.5
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        out.append(
            f'<text x="{LEFT - 8}" y="{sy(frac) + 4:.1f}" text-anchor="end" '
            f'fill="#555">{frac:.0%}</text>'
        )
    placed: list[tuple[float, float, float]] = []  # label boxes so far: x, y, width
    for name, p50, p95, rate, splits, pauses in sorted(points, key=lambda p: p[1]):
        text = f"{name} ({splits}/{pauses})"
        lx, ly, width = sx(p95) + 8, sy(rate) + 4, 7.0 * len(text)  # about 7 px per character
        while any(abs(ly - py) < 16 and lx < px + pw and px < lx + width for px, py, pw in placed):
            ly += 18  # stack downward until it clears the labels already drawn
        placed.append((lx, ly, width))
        y = sy(rate)
        out.append(
            f'<line x1="{sx(p50):.1f}" y1="{y:.1f}" x2="{sx(p95):.1f}" y2="{y:.1f}" '
            'stroke="#4c78a8" stroke-width="2"/>'
        )
        out.append(f'<circle cx="{sx(p50):.1f}" cy="{y:.1f}" r="5" fill="#4c78a8"/>')
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
