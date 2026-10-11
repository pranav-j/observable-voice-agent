import { CallControls } from './components/CallControls'
import { LatencyPanel } from './components/LatencyPanel'
import { OrderPanel } from './components/OrderPanel'
import { SummaryCard } from './components/SummaryCard'
import { Transcript } from './components/Transcript'

function App() {
  return (
    <main>
      <header>
        <h1>Juniper Street Kitchen</h1>
        <p className="muted">Order desk · voice agent</p>
      </header>
      <CallControls />
      <SummaryCard />
      <div className="grid">
        <Transcript />
        <div className="side">
          <OrderPanel />
          <LatencyPanel />
        </div>
      </div>
    </main>
  )
}

export default App
