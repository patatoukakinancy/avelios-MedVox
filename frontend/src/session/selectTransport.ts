import { openMockTransport } from './mockTransport'
import type { OpenTransport } from './transport'
import { openWebSocketTransport } from './webSocketTransport'

type TransportKind = 'mock' | 'ws'

// The real backend. ?transport=mock switches to the fake patient (no backend session, no API cost).
const DEFAULT_TRANSPORT: TransportKind = 'ws'

const requested = new URLSearchParams(window.location.search).get('transport')

export const transportKind: TransportKind =
  requested === 'mock' || requested === 'ws' ? requested : DEFAULT_TRANSPORT

export const openTransport: OpenTransport =
  transportKind === 'ws' ? openWebSocketTransport : openMockTransport
