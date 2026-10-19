"""`python -m voice_order.telemetry.dashboard` (or `make dashboard`): calls over time, as one page.

Phoenix shows one call at a time and the eval reports cover test runs. This puts every
recorded call side by side: calls per day and how they ended, how fast the agent answered,
what it cost, and how often a tool refused something. It reads only the files the worker
saves in recordings/, so it works offline. Real calls (from the web page) and simulated eval
calls are kept apart. The page holds no transcripts, names or phone numbers, only counts and
timings, and each call links to its trace in Phoenix when Phoenix can be reached.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

OUTCOMES = ("placed", "handed to a person", "not placed")
COLORS = {"placed": "#2e7d32", "handed to a person": "#ef6c00", "not placed": "#9e9e9e"}
PHOENIX_PROJECT = "voice-order-agent"


@dataclass
class Call:
    session_id: str
    kind: str  # "real" (from the web page) or "simulated" (an eval call)
    started: datetime
    seconds: float
    cost_usd: float | None
    outcome: str
    replies: list[float] = field(default_factory=list)  # agent-side reply latency, seconds
    tool_errors: int = 0
    speech: str = ""

    @property
    def day(self) -> str:
        return self.started.strftime("%Y-%m-%d")


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def outcome(tool_calls: list[dict[str, Any]]) -> str:
    done = {c["name"] for c in tool_calls if (c.get("result") or {}).get("ok")}
    if "confirm_order" in done:
        return "placed"
    if "transfer_to_human" in done:
        return "handed to a person"
    return "not placed"


def load_call(folder: Path) -> Call | None:
    """One recorded call, or None if the worker never saved it."""
    usage_file = folder / "usage.json"
    turns = _lines(folder / "turns.jsonl")
    if not usage_file.exists() or not turns:
        return None
    usage = json.loads(usage_file.read_text())
    tools = _lines(folder / "tool_calls.jsonl")
    config_file = folder / "config.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    if config:
        speech = f"{config.get('stt_provider', '?')}/{config.get('tts_provider', '?')}"
        if config.get("fault", "none") != "none":  # broken on purpose to test the evals
            speech += f", fault {config['fault']}"
    else:
        speech = "unknown"  # saved before the worker recorded its settings
    replies = [
        float(t["e2e_latency"])
        for t in turns
        if t.get("role") == "assistant" and isinstance(t.get("e2e_latency"), int | float)
    ]
    return Call(
        session_id=folder.name,
        kind="real" if folder.name.startswith("call-") else "simulated",
        started=datetime.fromtimestamp(min(float(t["created_at"]) for t in turns)),
        seconds=float(usage.get("duration_seconds") or 0.0),
        cost_usd=usage.get("total_cost_usd"),
        outcome=outcome(tools),
        replies=replies,
        tool_errors=sum(not (c.get("result") or {}).get("ok", True) for c in tools),
        speech=speech,
    )


def load_calls(recordings: Path) -> list[Call]:
    found = (load_call(d) for d in sorted(recordings.iterdir()) if d.is_dir())
    return sorted((c for c in found if c is not None), key=lambda c: c.started)


def percentile(values: list[float], p: float) -> float | None:
    """Nearest rank, like the eval reports."""
    if not values:
        return None
    ranked = sorted(values)
    return ranked[max(0, min(len(ranked) - 1, round(p / 100 * len(ranked) + 0.5) - 1))]


@dataclass
class Day:
    day: str
    calls: int
    outcomes: dict[str, int]
    p50: float | None
    p95: float | None
    cost_per_minute: float | None
    tool_errors_per_call: float


def by_day(calls: list[Call]) -> list[Day]:
    days: dict[str, list[Call]] = defaultdict(list)
    for c in calls:
        days[c.day].append(c)
    out = []
    for day, group in sorted(days.items()):
        replies = [r for c in group for r in c.replies]
        priced = [c for c in group if c.cost_usd is not None and c.seconds > 0]
        minutes = sum(c.seconds for c in priced) / 60
        cost = sum(float(c.cost_usd or 0) for c in priced)
        out.append(
            Day(
                day=day,
                calls=len(group),
                outcomes={o: sum(c.outcome == o for c in group) for o in OUTCOMES},
                p50=percentile(replies, 50),
                p95=percentile(replies, 95),
                cost_per_minute=cost / minutes if minutes else None,
                tool_errors_per_call=sum(c.tool_errors for c in group) / len(group),
            )
        )
    return out


def phoenix_traces(base_url: str, timeout: float = 5.0) -> dict[str, str]:
    """session id -> trace id, from Phoenix. Empty if Phoenix isn't reachable.

    Asks for the agent_session spans only, so it doesn't page through every span.
    """
    query = """query($after: String) { projects { edges { node { name spans(first: 1000,
      after: $after, filterCondition: "name == 'agent_session'") {
      edges { node { context { traceId } attributes } } pageInfo { hasNextPage endCursor }
    } } } } }"""
    traces: dict[str, str] = {}
    after: str | None = None
    try:
        for _ in range(100):
            body = json.dumps({"query": query, "variables": {"after": after}}).encode()
            request = urllib.request.Request(
                f"{base_url}/graphql", data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                reply = json.load(response)
            if reply.get("errors"):
                print(f"Phoenix: {reply['errors'][0].get('message')}", file=sys.stderr)
                return traces
            data = reply["data"]["projects"]["edges"]
            project = next(e["node"] for e in data if e["node"]["name"] == PHOENIX_PROJECT)
            for edge in project["spans"]["edges"]:
                attributes = json.loads(edge["node"]["attributes"] or "{}")
                if session := attributes.get("session_id"):
                    traces[session] = edge["node"]["context"]["traceId"]
            page = project["spans"]["pageInfo"]
            if not page["hasNextPage"]:
                break
            after = page["endCursor"]
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return traces
    return traces


# --- the page -------------------------------------------------------------------------------


def _fmt_s(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} s"


def _bars(days: list[Day], width: int = 720, height: int = 180) -> str:
    """Calls per day, stacked by outcome."""
    if not days:
        return ""
    top = max(d.calls for d in days)
    slot = width / len(days)
    bar = max(4.0, min(36.0, slot * 0.7))
    parts = []
    for i, d in enumerate(days):
        x, y = i * slot + (slot - bar) / 2, float(height)
        for o in OUTCOMES:
            h = d.outcomes[o] / top * (height - 10)
            if h:
                y -= h
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar:.1f}" height="{h:.1f}" '
                    f'fill="{COLORS[o]}"><title>{d.day}: {d.outcomes[o]} {o}</title></rect>'
                )
    return _svg(parts, days, width, height, f"{top} calls")


def _lines_chart(days: list[Day], width: int = 720, height: int = 180) -> str:
    """Agent reply latency per day: p50 and p95."""
    values = [v for d in days for v in (d.p50, d.p95) if v is not None]
    if not values:
        return ""
    top = max(values)
    slot = width / len(days)
    parts = []
    for key, color in (("p50", "var(--accent)"), ("p95", "var(--muted)")):
        points = [
            (i * slot + slot / 2, height - getattr(d, key) / top * (height - 10), d)
            for i, d in enumerate(days)
            if getattr(d, key) is not None
        ]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        parts += [
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}">'
            f"<title>{d.day} {key}: {getattr(d, key):.2f} s</title></circle>"
            for x, y, d in points
        ]
    return _svg(parts, days, width, height, f"{top:.1f} s")


def _svg(parts: list[str], days: list[Day], width: int, height: int, top_label: str) -> str:
    slot = width / len(days)
    every = max(1, len(days) // 8)
    labels = [
        f'<text x="{i * slot + slot / 2:.1f}" y="{height + 16}" text-anchor="middle">'
        f"{d.day[5:]}</text>"
        for i, d in enumerate(days)
        if i % every == 0
    ]
    return (
        f'<svg viewBox="0 -14 {width} {height + 34}" role="img" class="chart">'
        f'<text x="0" y="-2" class="axis">{escape(top_label)}</text>'
        f'<line x1="0" y1="{height}" x2="{width}" y2="{height}" class="base"/>'
        + "".join(parts)
        + "".join(labels)
        + "</svg>"
    )


def _section(title: str, calls: list[Call], traces: dict[str, str], phoenix: str) -> str:
    if not calls:
        return f"<section><h2>{escape(title)}</h2><p class='muted'>No calls recorded.</p></section>"
    days = by_day(calls)
    replies = [r for c in calls for r in c.replies]
    placed = sum(c.outcome == "placed" for c in calls)
    priced = [c for c in calls if c.cost_usd is not None and c.seconds > 0]
    minutes = sum(c.seconds for c in priced) / 60
    cost = sum(float(c.cost_usd or 0) for c in priced)
    tiles = [
        ("Calls", f"{len(calls)}"),
        ("Orders placed", f"{placed} ({placed / len(calls):.0%})"),
        (
            "Reply p50 / p95",
            f"{_fmt_s(percentile(replies, 50))} / {_fmt_s(percentile(replies, 95))}",
        ),
        ("Cost per minute", f"${cost / minutes:.4f}" if minutes else "n/a"),
        ("Tool errors per call", f"{sum(c.tool_errors for c in calls) / len(calls):.2f}"),
    ]
    legend = "".join(
        f'<span><i style="background:{COLORS[o]}"></i>{escape(o)}</span>' for o in OUTCOMES
    )
    rows = []
    for c in reversed(calls[-40:]):
        trace = traces.get(c.session_id)
        link = (
            f'<a href="{phoenix}/projects/{PHOENIX_PROJECT}/traces/{trace}">trace</a>'
            if trace
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{c.started:%Y-%m-%d %H:%M}</td><td class='id'>{escape(c.session_id)}</td>"
            f"<td>{c.seconds / 60:.1f} min</td><td>{escape(c.outcome)}</td>"
            f"<td>{_fmt_s(percentile(c.replies, 50))}</td>"
            f"<td>{'n/a' if c.cost_usd is None else f'${float(c.cost_usd):.4f}'}</td>"
            f"<td>{c.tool_errors}</td><td>{escape(c.speech)}</td><td>{link}</td>"
            "</tr>"
        )
    tile_html = "".join(f"<div><b>{escape(v)}</b><span>{escape(k)}</span></div>" for k, v in tiles)
    by_outcome = "Calls per day, by how they ended"
    latency = 'Agent reply latency per day: <b class="p50">p50</b> and <b class="p95">p95</b>'
    return f"""<section>
<h2>{escape(title)}</h2>
<div class="tiles">{tile_html}</div>
<div class="charts">
<figure><figcaption>{by_outcome}</figcaption>{_bars(days)}
<div class="legend">{legend}</div></figure>
<figure><figcaption>{latency}</figcaption>{_lines_chart(days)}</figure>
</div>
<h3>Latest calls</h3>
<table><thead><tr><th>Started</th><th>Session</th><th>Length</th><th>Outcome</th>
<th>Reply p50</th><th>Cost</th><th>Tool errors</th><th>Setup</th><th></th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
</section>"""


STYLE = """
:root {
  --bg:#f6f7f9;
  --card:#fff;
  --text:#1d2330;
  --muted:#8a93a3;
  --accent:#3366cc;
  --line:#e3e6ec;
}
@media (prefers-color-scheme: dark) {
:root {
  --bg:#13161c;
  --card:#1c2029;
  --text:#e6e9ef;
  --muted:#7d879a;
  --accent:#7aa2f7;
  --line:#2b313d;
}
}
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--text);
  font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:17px; margin:0 0 12px; }
h3 { font-size:14px; }
.muted, .sub { color:var(--muted); }
section {
  background:var(--card);
  border:1px solid var(--line);
  border-radius:10px;
  padding:18px;
  margin:18px 0;
}
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:10px; }
.tiles div { border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
.tiles b { display:block; font-size:18px; } .tiles span { color:var(--muted); font-size:12px; }
.charts {
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));
  gap:18px;
  margin-top:16px;
}
figure { margin:0; } figcaption { color:var(--muted); font-size:12px; margin-bottom:6px; }
.chart { width:100%; height:auto; overflow:visible; }
.chart text { fill:var(--muted); font-size:11px; } .chart .base { stroke:var(--line); }
.p50 { color:var(--accent); } .p95 { color:var(--muted); }
.legend { display:flex; gap:14px; font-size:12px; color:var(--muted); margin-top:4px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th, td {
  text-align:left;
  padding:6px 8px;
  border-bottom:1px solid var(--line);
  white-space:nowrap;
}
th { color:var(--muted); font-weight:600; }
td.id { font-family:ui-monospace, Menlo, monospace; font-size:11.5px; }
.tablewrap { overflow-x:auto; } a { color:var(--accent); }
"""


def render(calls: list[Call], traces: dict[str, str], phoenix: str, source: str) -> str:
    real = [c for c in calls if c.kind == "real"]
    simulated = [c for c in calls if c.kind == "simulated"]
    sections = _section("Real calls, from the web page", real, traces, phoenix) + _section(
        "Simulated calls, from the eval harness", simulated, traces, phoenix
    )
    sections = sections.replace("<table>", '<div class="tablewrap"><table>').replace(
        "</table>", "</table></div>"
    )
    linked = sum(c.session_id in traces for c in calls)
    note = (
        f"{linked} of {len(calls)} calls link to their trace in Phoenix."
        if traces
        else "Phoenix wasn't reachable, so calls don't link to their traces."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice agent calls</title><style>{STYLE}</style></head>
<body><main>
<h1>Voice agent calls</h1>
<p class="sub">{len(calls)} recorded calls in <code>{escape(source)}</code>,
built {datetime.now():%Y-%m-%d %H:%M}.
Reply latency is the agent's own end-to-end time per reply. Outcomes come from the tool calls.
{escape(note)}</p>
{sections}
</main></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m voice_order.telemetry.dashboard")
    p.add_argument("--recordings", type=Path, default=Path("recordings"))
    p.add_argument("--out", type=Path, default=Path("dashboard/index.html"))
    p.add_argument("--phoenix", default="http://localhost:6006", help="'' to skip trace links")
    args = p.parse_args(argv)
    if not args.recordings.is_dir():
        print(f"No recordings at {args.recordings}.", file=sys.stderr)
        return 2
    calls = load_calls(args.recordings)
    traces = phoenix_traces(args.phoenix) if args.phoenix else {}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(calls, traces, args.phoenix, str(args.recordings)), encoding="utf-8")
    real = sum(c.kind == "real" for c in calls)
    print(f"Wrote {args.out}: {len(calls)} calls ({real} real), {len(traces)} with traces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
