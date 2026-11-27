import { useEffect, useReducer, useRef } from 'react'
import type { PatientSummary, PublicCard, Role, ServerMessage } from '../protocol'
import { openMockTransport } from './mockTransport'
import type { Transport } from './transport'

export interface TranscriptItem {
  item_id: string
  role: Role
  text: string
}

export interface SessionState {
  status: 'connecting' | 'ready' | 'ended'
  card: PublicCard | null
  transcript: TranscriptItem[]
  error: string | null
  endedReason: string | null
}

const initialState: SessionState = {
  status: 'connecting',
  card: null,
  transcript: [],
  error: null,
  endedReason: null,
}

function upsert(
  items: TranscriptItem[],
  next: TranscriptItem,
  mode: 'append' | 'replace',
): TranscriptItem[] {
  if (!items.some((item) => item.item_id === next.item_id)) return [...items, next]
  return items.map((item) => {
    if (item.item_id !== next.item_id) return item
    return { ...item, text: mode === 'append' ? item.text + next.text : next.text }
  })
}

function reducer(state: SessionState, message: ServerMessage): SessionState {
  switch (message.type) {
    case 'session.ready':
      return { ...state, status: 'ready', card: message.patient_public }
    case 'transcript.delta':
    case 'transcript.final': {
      const { item_id, role, text } = message
      // Assumes delta text is incremental (to be confirmed with the backend).
      const mode = message.type === 'transcript.delta' ? 'append' : 'replace'
      return { ...state, transcript: upsert(state.transcript, { item_id, role, text }, mode) }
    }
    case 'error':
      return { ...state, error: `${message.code}: ${message.message}` }
    case 'session.ended':
      return { ...state, status: 'ended', endedReason: message.reason }
    // Voice mode and latency are not handled yet.
    case 'speech.started':
    case 'audio.delta':
    case 'latency':
      return state
  }
}

// One hook instance is one session: remount the component to start a new one.
export function useSession(patient: PatientSummary) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const transportRef = useRef<Transport | null>(null)

  useEffect(() => {
    const transport = openMockTransport(patient, dispatch)
    transportRef.current = transport
    return () => transport.close()
  }, [patient])

  return {
    ...state,
    sendText: (text: string) => transportRef.current?.send({ type: 'text.send', text }),
    endSession: () => transportRef.current?.send({ type: 'session.end' }),
  }
}
