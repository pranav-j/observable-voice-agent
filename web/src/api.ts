// The backend: join tokens and saved calls. Shapes mirror voice_order.api.app.

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type TokenResponse = { url: string; token: string; room: string; identity: string }

export type OrderLine = {
  line_id: number
  description: string
  item_id: string
  quantity: number
  line_total: string
}

export type OrderView = {
  status: 'draft' | 'confirmed' | 'abandoned' | 'escalated'
  lines: OrderLine[]
  total: string
  customer: { name: string; phone: string } | null
  readback_current: boolean
}

export type CallSummary = {
  session_id: string
  order: OrderView
  saved: boolean
  duration_seconds: number | null
  turns: number
  cost_usd: number | null
  cost_is_estimate: boolean
}

export async function fetchToken(): Promise<TokenResponse> {
  const response = await fetch(`${API}/token`, { method: 'POST' })
  if (!response.ok) throw new Error(`token request failed: ${response.status}`)
  return (await response.json()) as TokenResponse
}

export async function fetchCall(sessionId: string): Promise<CallSummary | null> {
  const response = await fetch(`${API}/calls/${encodeURIComponent(sessionId)}`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`call summary failed: ${response.status}`)
  return (await response.json()) as CallSummary
}
