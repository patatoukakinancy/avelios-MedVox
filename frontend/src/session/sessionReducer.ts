import type { PublicCard, Role, SessionMode } from '../protocol'
import type { SessionEvent } from './transport'

export interface TranscriptItem {
  item_id: string
  role: Role
  text: string
  // A question shown before the server has sent its own transcript of it.
  pending?: boolean
}

export interface SessionState {
  status: 'connecting' | 'ready' | 'ended'
  card: PublicCard | null
  // The mode the server actually opened; voice can fall back to text.
  mode: SessionMode | null
  // A typed question is waiting for the end of the patient's reply.
  awaitingReply: boolean
  transcript: TranscriptItem[]
  error: string | null
  endedReason: string | null
}

export type SessionAction = SessionEvent | { type: 'local.sent'; item_id: string; text: string }

export const initialState: SessionState = {
  status: 'connecting',
  card: null,
  mode: null,
  awaitingReply: false,
  transcript: [],
  error: null,
  endedReason: null,
}

const ERROR_TEXT: Record<string, string> = {
  busy: 'Another consultation is already running. Please try again in a moment.',
  bad_message: 'The server could not read the last message.',
  upstream_closed: 'The patient service disconnected. Please start a new consultation.',
  not_found: 'This patient is not available.',
  budget_exhausted: 'The usage limit has been reached.',
}

function upsert(
  items: TranscriptItem[],
  next: TranscriptItem,
  mode: 'append' | 'replace',
): TranscriptItem[] {
  if (items.some((item) => item.item_id === next.item_id)) {
    return items.map((item) => {
      if (item.item_id !== next.item_id) return item
      return { ...item, text: mode === 'append' ? item.text + next.text : next.text }
    })
  }
  // The server's copy of a question takes the place of the oldest pending one.
  const pending = next.role === 'user' ? items.findIndex((item) => item.pending) : -1
  if (pending !== -1) return items.with(pending, next)
  return [...items, next]
}

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'local.sent': {
      const item: TranscriptItem = { item_id: action.item_id, role: 'user', text: action.text, pending: true }
      return { ...state, error: null, awaitingReply: true, transcript: [...state.transcript, item] }
    }
    case 'session.ready':
      return { ...state, status: 'ready', card: action.patient_public, mode: action.mode ?? null }
    case 'transcript.delta':
    case 'transcript.final': {
      const { item_id, role, text } = action
      // Assumes delta text is incremental (to be confirmed with the backend).
      const mode = action.type === 'transcript.delta' ? 'append' : 'replace'
      return { ...state, transcript: upsert(state.transcript, { item_id, role, text }, mode) }
    }
    case 'error':
      return {
        ...state,
        awaitingReply: false,
        error: Object.hasOwn(ERROR_TEXT, action.code) ? ERROR_TEXT[action.code] : action.message,
      }
    // The server sends latency once the whole reply is done.
    case 'latency':
      return state.awaitingReply ? { ...state, awaitingReply: false } : state
    case 'session.ended':
      return { ...state, status: 'ended', endedReason: action.reason }
    case 'connection.lost':
      return {
        ...state,
        status: 'ended',
        endedReason: 'connection lost',
        // Keep a more specific error from the server if there is one.
        error: state.error ?? 'Lost the connection to the server.',
      }
    // Audio is handled outside React state (useVoice).
    case 'speech.started':
    case 'audio.delta':
      return state
  }
}
