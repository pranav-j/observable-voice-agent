import { useCallStore } from '../store/call'

export function OrderPanel() {
  const order = useCallStore((s) => s.order)
  return (
    <section className="card order">
      <h2>
        Order {order && <span className={`badge ${order.status}`}>{order.status}</span>}
      </h2>
      {!order || order.lines.length === 0 ? (
        <p className="muted">No items yet.</p>
      ) : (
        <table>
          <tbody>
            {order.lines.map((line) => (
              <tr key={line.line_id}>
                <td>{line.description}</td>
                <td className="num">{line.line_total}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th>Total</th>
              <th className="num">{order.total}</th>
            </tr>
          </tfoot>
        </table>
      )}
      {order?.customer && (
        <p className="muted">
          For {order.customer.name}, {order.customer.phone}
          {order.readback_current && ' · read back'}
        </p>
      )}
    </section>
  )
}
