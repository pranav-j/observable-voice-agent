import { useCallStore } from './store/call'

function App() {
  const status = useCallStore((s) => s.status)

  return (
    <main>
      <h1>Juniper Street Kitchen</h1>
      <p className="subtitle">Order desk</p>
      <p>
        Call status: <code>{status}</code>
      </p>
    </main>
  )
}

export default App
