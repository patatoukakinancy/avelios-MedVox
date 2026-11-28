import type { PublicCard, Role, SessionMode } from '../protocol'
import type { SessionEvent } from './transport'

export interface TranscriptItem {
  item_id: string
  role: Role
  text: string
  // A question shown before the server has sent its own transcript of it.
  pending?: boolean
  // Voice: a "…" line that holds the place of speech not yet transcribed.
  heldSince?: number
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

export type SessionAction =
  | Exclude<SessionEvent, { type: 'speech.started' }>
  | { type: 'speech.started'; at: number }
  | { type: 'local.sent'; item_id: string; text: string }

// A transcript normally arrives within seconds. A "…" line older than this is given up, so
// that it cannot take the text of a later question.
const STALE_PLACEHOLDER_MS = 20_000

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

// The student started talking: hold their place, so that a late transcript still appears
// above the patient's reply.
function holdPlace(items: TranscriptItem[], at: number): TranscriptItem[] {
  const kept = items.filter((item) => item.heldSince === undefined || at - item.heldSince < STALE_PLACEHOLDER_MS)
  if (kept.at(-1)?.heldSince !== undefined) return kept
  return [...kept, { item_id: `speech_${at}`, role: 'user', text: '…', pending: true, heldSince: at }]
}

// Speech with no words (for example noise): remove its line.
function dropEmptySpeech(items: TranscriptItem[], item_id: string): TranscriptItem[] {
  let index = items.findIndex((item) => item.item_id === item_id)
  if (index === -1) index = items.findIndex((item) => item.heldSince !== undefined)
  return index === -1 ? items : items.toSpliced(index, 1)
}

// "…" lines that never got their text disappear when the session ends.
const withoutPlaceholders = (items: TranscriptItem[]) => items.filter((item) => item.heldSince === undefined)

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
      if (role === 'user' && !text.trim()) {
        if (action.type === 'transcript.delta') return state
        return { ...state, transcript: dropEmptySpeech(state.transcript, item_id) }
      }
      // Delta text is incremental: the backend forwards upstream deltas as they are.
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
    case 'speech.started':
      return { ...state, transcript: holdPlace(state.transcript, action.at) }
    case 'session.ended':
      return {
        ...state,
        status: 'ended',
        endedReason: action.reason,
        transcript: withoutPlaceholders(state.transcript),
      }
    case 'connection.lost':
      return {
        ...state,
        status: 'ended',
        transcript: withoutPlaceholders(state.transcript),
        endedReason: 'connection lost',
        // Keep a more specific error from the server if there is one.
        error: state.error ?? 'Lost the connection to the server.',
      }
    // Audio is handled outside React state (useVoice).
    case 'audio.delta':
      return state
  }
}
