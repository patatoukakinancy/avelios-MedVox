import type { ClientMessage, PatientSummary, ServerMessage, SessionMode } from '../protocol'

// 'connection.lost' is produced by the frontend only; it is not part of CONTRACT.md.
export type SessionEvent = ServerMessage | { type: 'connection.lost' }

export interface Transport {
  send(message: ClientMessage): void
  close(): void
}

// Implemented by both the mock and the WebSocket transport.
export type OpenTransport = (
  patient: PatientSummary,
  mode: SessionMode,
  onEvent: (event: SessionEvent) => void,
) => Transport
