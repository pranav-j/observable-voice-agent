import { create } from 'zustand'

export type CallStatus = 'idle' | 'connecting' | 'in_call' | 'ended'

type CallState = {
  status: CallStatus
  setStatus: (status: CallStatus) => void
}

export const useCallStore = create<CallState>()((set) => ({
  status: 'idle',
  setStatus: (status) => set({ status }),
}))
