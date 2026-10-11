import { create } from 'zustand'
import type { CallSummary, OrderView } from '../api'
import type { TurnRecord } from '../stats'

export type CallStatus = 'idle' | 'connecting' | 'in_call' | 'ended' | 'error'

export type TranscriptLine = { id: number; who: 'caller' | 'agent'; text: string; at: number }

type CallState = {
  status: CallStatus
  room: string | null
  startedAt: number | null
  error: string | null
  transcript: TranscriptLine[]
  order: OrderView | null
  turns: TurnRecord[]
  summary: CallSummary | null
  begin: (room: string) => void
  setStatus: (status: CallStatus) => void
  fail: (error: string) => void
  say: (who: TranscriptLine['who'], text: string) => void
  setOrder: (order: OrderView) => void
  addTurn: (turn: TurnRecord) => void
  setSummary: (summary: CallSummary) => void
}

let nextLine = 0

export const useCallStore = create<CallState>()((set) => ({
  status: 'idle',
  room: null,
  startedAt: null,
  error: null,
  transcript: [],
  order: null,
  turns: [],
  summary: null,
  begin: (room) =>
    set({ status: 'connecting', room, startedAt: Date.now(), error: null, transcript: [], order: null, turns: [], summary: null }),
  setStatus: (status) => set({ status }),
  fail: (error) => set({ status: 'error', error }),
  say: (who, text) =>
    set((s) => ({ transcript: [...s.transcript, { id: nextLine++, who, text, at: Date.now() }] })),
  setOrder: (order) => set({ order }),
  addTurn: (turn) => set((s) => ({ turns: [...s.turns, turn] })),
  setSummary: (summary) => set({ summary }),
}))
