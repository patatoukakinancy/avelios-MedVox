import type { ServerMessage } from '../protocol'

type Fields = Record<string, unknown>

const isObject = (value: unknown): value is Fields => typeof value === 'object' && value !== null
const isString = (value: unknown) => typeof value === 'string'

const isTranscript = (m: Fields) =>
  (m.role === 'user' || m.role === 'patient') && isString(m.item_id) && isString(m.text)

// Checks only the fields the frontend relies on.
const VALIDATORS: Record<ServerMessage['type'], (m: Fields) => boolean> = {
  'session.ready': (m) => isObject(m.patient_public) && isString(m.patient_public.display_name),
  'speech.started': () => true,
  'audio.delta': (m) => isString(m.audio),
  'transcript.delta': isTranscript,
  'transcript.final': isTranscript,
  latency: () => true,
  error: (m) => isString(m.code) && isString(m.message),
  'session.ended': (m) => isString(m.reason),
}

// Returns null for anything that does not match CONTRACT.md.
export function parseServerMessage(data: unknown): ServerMessage | null {
  if (typeof data !== 'string') return null
  try {
    const message: unknown = JSON.parse(data)
    if (!isObject(message) || typeof message.type !== 'string') return null
    if (!Object.hasOwn(VALIDATORS, message.type)) return null
    const isValid = VALIDATORS[message.type as ServerMessage['type']]
    return isValid(message) ? (message as unknown as ServerMessage) : null
  } catch {
    return null
  }
}
