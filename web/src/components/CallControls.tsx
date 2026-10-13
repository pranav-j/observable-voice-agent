import { endCall, startCall } from '../livekit'
import { useCallStore } from '../store/call'

const LABELS = { idle: 'Ready', connecting: 'Connecting…', in_call: 'On call', ended: 'Call ended', error: 'Error' }

export function CallControls() {
  const status = useCallStore((s) => s.status)
  const room = useCallStore((s) => s.room)
  const error = useCallStore((s) => s.error)
  const live = status === 'connecting' || status === 'in_call'
  return (
    <section className="card controls">
      <div>
        <span className={`dot ${status}`} aria-hidden /> <strong>{LABELS[status]}</strong>
        {room && <code className="muted"> {room}</code>}
        {error && <p className="error">{error}</p>}
        <p className="muted">
          Calls are recorded to test the agent and deleted after 7 days. Use a made-up name and phone number.
        </p>
      </div>
      {live ? (
        <button className="danger" onClick={() => void endCall()}>
          End call
        </button>
      ) : (
        <button onClick={() => void startCall()}>Start call</button>
      )}
    </section>
  )
}
