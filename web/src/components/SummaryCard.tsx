import { useCallStore } from '../store/call'

export function SummaryCard() {
  const summary = useCallStore((s) => s.summary)
  const status = useCallStore((s) => s.status)
  if (status !== 'ended') return null
  if (!summary) return <section className="card summary muted">Fetching the call summary…</section>
  const { order } = summary
  return (
    <section className="card summary">
      <h2>Call summary</h2>
      <dl className="stats">
        <div>
          <dt>order</dt>
          <dd>{order.status}</dd>
        </div>
        <div>
          <dt>duration</dt>
          <dd>{summary.duration_seconds === null ? '…' : `${Math.round(summary.duration_seconds)} s`}</dd>
        </div>
        <div>
          <dt>turns</dt>
          <dd>{summary.turns}</dd>
        </div>
        <div>
          <dt>est. cost</dt>
          <dd>
            {summary.cost_usd === null ? '…' : `$${summary.cost_usd.toFixed(3)}`}
            {summary.cost_is_estimate && ' *'}
          </dd>
        </div>
      </dl>
      <p className="muted">
        {order.lines.map((l) => l.description).join(', ') || 'No items'} · {order.total}
      </p>
      {summary.cost_is_estimate && <p className="muted">* speech-to-text cost estimated from call length</p>}
    </section>
  )
}
