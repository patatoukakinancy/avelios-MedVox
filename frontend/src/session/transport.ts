import type { ClientMessage, PatientSummary, ServerMessage } from '../protocol'

export interface Transport {
  send(message: ClientMessage): void
  close(): void
}

// The real WebSocket client will implement this same signature.
export type OpenTransport = (
  patient: PatientSummary,
  onMessage: (message: ServerMessage) => void,
) => Transport
