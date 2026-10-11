// Latency maths for the overlay. Records come from the worker's "turn" topic: the same
// numbers written to turns.jsonl and attached to the traces in Phoenix.

export type TurnRecord = {
  turn_index: number
  role: string
  text: string
  interrupted: boolean
  created_at: number
  transcription_delay?: number
  end_of_turn_delay?: number
  llm_node_ttft?: number
  tts_node_ttfb?: number
  e2e_latency?: number
}

/** Nearest-rank percentile, defined the same way as the eval reports. */
export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const rank = Math.max(1, Math.ceil((p / 100) * sorted.length))
  return sorted[rank - 1]
}

export function responseLatencies(turns: TurnRecord[]): number[] {
  return turns
    .filter((t) => t.role === 'assistant' && t.e2e_latency !== undefined)
    .map((t) => t.e2e_latency as number)
}

export type Segment = { label: string; start: number; end: number }

/**
 * Bars for one turn, in seconds after the caller stopped speaking.
 * Transcription runs alongside end-of-turn detection; the LLM starts once the turn ends,
 * and speech once the first sentence is ready. Anything left (tool calls, extra LLM
 * rounds) shows as its own bar so the total adds up.
 */
export function waterfall(user: TurnRecord | undefined, agent: TurnRecord): { segments: Segment[]; total: number } {
  const eot = user?.end_of_turn_delay ?? 0
  const stt = user?.transcription_delay ?? 0
  const ttft = agent.llm_node_ttft ?? 0
  const ttfb = agent.tts_node_ttfb ?? 0
  const total = agent.e2e_latency ?? eot + ttft + ttfb
  const segments: Segment[] = [
    { label: 'Transcript', start: 0, end: stt },
    { label: 'End of turn', start: 0, end: eot },
  ]
  const known = eot + ttft + ttfb
  if (total > known + 0.05) segments.push({ label: 'Tools & extra LLM rounds', start: eot, end: eot + (total - known) })
  const llmStart = eot + Math.max(0, total - known)
  segments.push({ label: 'LLM first token', start: llmStart, end: llmStart + ttft })
  segments.push({ label: 'TTS first audio', start: llmStart + ttft, end: llmStart + ttft + ttfb })
  return { segments, total }
}

/** The most recent agent reply that has timings, with the caller turn before it. */
export function lastTurn(turns: TurnRecord[]): { user?: TurnRecord; agent: TurnRecord } | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    const agent = turns[i]
    if (agent.role !== 'assistant' || agent.e2e_latency === undefined) continue
    const user = turns.slice(0, i).reverse().find((t) => t.role === 'user' && t.turn_index === agent.turn_index)
    return { user, agent }
  }
  return null
}
