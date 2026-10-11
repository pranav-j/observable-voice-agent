// Connects the browser to a call: microphone out, agent audio in, plus the live
// transcript (LiveKit's transcription stream) and the worker's order and turn updates.

import { Room, RoomEvent, Track, type RemoteTrack } from 'livekit-client'
import { fetchCall, fetchToken, type OrderView } from './api'
import { useCallStore } from './store/call'
import type { TurnRecord } from './stats'

let room: Room | null = null
const decoder = new TextDecoder()

export async function startCall(): Promise<void> {
  const store = useCallStore.getState()
  try {
    const { url, token, room: name, identity } = await fetchToken()
    store.begin(name)
    room = new Room()
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Audio) document.body.appendChild(track.attach())
    })
    room.registerTextStreamHandler('lk.transcription', async (reader, participant) => {
      const text = (await reader.readAll()).trim()
      const final = reader.info.attributes?.['lk.transcription_final'] === 'true'
      if (final && text) useCallStore.getState().say(participant.identity === identity ? 'caller' : 'agent', text)
    })
    room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      const data: unknown = JSON.parse(decoder.decode(payload))
      if (topic === 'order') useCallStore.getState().setOrder(data as OrderView)
      if (topic === 'turn') useCallStore.getState().addTurn(data as TurnRecord)
    })
    room.on(RoomEvent.Disconnected, () => void finish(name))
    await room.connect(url, token)
    await room.localParticipant.setMicrophoneEnabled(true)
    useCallStore.getState().setStatus('in_call')
  } catch (err) {
    useCallStore.getState().fail(err instanceof Error ? err.message : String(err))
    await room?.disconnect()
  }
}

export async function endCall(): Promise<void> {
  await room?.disconnect()
}

async function finish(sessionId: string): Promise<void> {
  room = null
  useCallStore.getState().setStatus('ended')
  // The worker saves duration and cost when the call ends; poll briefly for them.
  for (let attempt = 0; attempt < 15; attempt++) {
    const summary = await fetchCall(sessionId).catch(() => null)
    if (summary) useCallStore.getState().setSummary(summary)
    if (summary?.saved) return
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}
