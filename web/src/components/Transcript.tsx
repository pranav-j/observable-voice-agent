import { useEffect, useRef } from 'react'
import { useCallStore } from '../store/call'

export function Transcript() {
  const lines = useCallStore((s) => s.transcript)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from scrollIntoView, and an
    // effect must return nothing or a cleanup function, or React crashes on unmount.
    void end.current?.scrollIntoView({ block: 'nearest' })
  }, [lines])
  return (
    <section className="card transcript">
      <h2>Transcript</h2>
      {lines.length === 0 && <p className="muted">Start a call and say what you'd like to order.</p>}
      <ol>
        {lines.map((line) => (
          <li key={line.id} className={line.who}>
            <span className="who">{line.who === 'agent' ? 'Agent' : 'You'}</span> {line.text}
          </li>
        ))}
      </ol>
      <div ref={end} />
    </section>
  )
}
