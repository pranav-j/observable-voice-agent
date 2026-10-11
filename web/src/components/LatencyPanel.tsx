import { lastTurn, percentile, responseLatencies, waterfall } from '../stats'
import { useCallStore } from '../store/call'

const fmt = (s: number | null) => (s === null ? '–' : `${s.toFixed(2)} s`)

export function LatencyPanel() {
  const turns = useCallStore((s) => s.turns)
  const latest = lastTurn(turns)
  const latencies = responseLatencies(turns)
  const view = latest ? waterfall(latest.user, latest.agent) : null
  const scale = view ? Math.max(view.total, ...view.segments.map((s) => s.end), 0.001) : 1
  return (
    <section className="card latency">
      <h2>Latency</h2>
      <dl className="stats">
        <div>
          <dt>p50</dt>
          <dd>{fmt(percentile(latencies, 50))}</dd>
        </div>
        <div>
          <dt>p95</dt>
          <dd>{fmt(percentile(latencies, 95))}</dd>
        </div>
        <div>
          <dt>replies</dt>
          <dd>{latencies.length}</dd>
        </div>
      </dl>
      {!view ? (
        <p className="muted">Timings appear after the agent's first reply.</p>
      ) : (
        <>
          <p className="muted">Last turn: {fmt(view.total)} from the end of your speech to the agent's voice.</p>
          <ul className="waterfall">
            {view.segments.map((seg) => (
              <li key={seg.label}>
                <span className="label">{seg.label}</span>
                <span className="track">
                  <span
                    className="bar"
                    style={{ left: `${(seg.start / scale) * 100}%`, width: `${Math.max(((seg.end - seg.start) / scale) * 100, 0.5)}%` }}
                  />
                </span>
                <span className="value">{fmt(seg.end - seg.start)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
