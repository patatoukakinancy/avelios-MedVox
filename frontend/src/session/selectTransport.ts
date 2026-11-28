import { openMockTransport } from './mockTransport'
import type { OpenTransport } from './transport'
import { openWebSocketTransport } from './webSocketTransport'

type TransportKind = 'mock' | 'ws'

// Switch to 'ws' once the backend serves /ws/session. ?transport=mock|ws overrides it.
const DEFAULT_TRANSPORT: TransportKind = 'mock'

const requested = new URLSearchParams(window.location.search).get('transport')

export const transportKind: TransportKind =
  requested === 'mock' || requested === 'ws' ? requested : DEFAULT_TRANSPORT

export const openTransport: OpenTransport =
  transportKind === 'ws' ? openWebSocketTransport : openMockTransport
