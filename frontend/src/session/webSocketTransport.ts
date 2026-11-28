import type { ClientMessage, SessionMode } from '../protocol'
import { parseServerMessage } from './parseServerMessage'
import type { OpenTransport } from './transport'

const READY_TIMEOUT_MS = 10_000
const END_TIMEOUT_MS = 3_000

function sessionUrl(patientId: string, mode: SessionMode) {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const query = new URLSearchParams({ patient_id: patientId, mode })
  return `${scheme}://${window.location.host}/ws/session?${query}`
}

export const openWebSocketTransport: OpenTransport = (patient, mode, onEvent) => {
  let socket: WebSocket | null = null
  // Set once the session is over or the caller closed it: no more events after that.
  let done = false
  let readyTimer: number | undefined
  let endTimer: number | undefined

  function finish() {
    done = true
    window.clearTimeout(connectTimer)
    window.clearTimeout(readyTimer)
    window.clearTimeout(endTimer)
    socket?.close()
  }

  function lose() {
    if (done) return
    finish()
    onEvent({ type: 'connection.lost' })
  }

  function transmit(message: ClientMessage) {
    if (socket?.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(message))
    return true
  }

  // Connect on the next tick: React StrictMode mounts, closes and mounts again,
  // and only one backend session may be active at a time.
  const connectTimer = window.setTimeout(() => {
    socket = new WebSocket(sessionUrl(patient.patient_id, mode))
    readyTimer = window.setTimeout(lose, READY_TIMEOUT_MS)

    socket.onmessage = (event) => {
      if (done) return
      const message = parseServerMessage(event.data)
      if (!message) {
        console.warn('[ws] ignored message', event.data)
        return
      }
      // Audio chunks are left out: they would flood the console.
      if (import.meta.env.DEV && message.type !== 'audio.delta') console.debug('[ws]', message)
      if (message.type === 'session.ready') window.clearTimeout(readyTimer)
      if (message.type === 'session.ended') finish()
      onEvent(message)
    }
    // A failed or dropped connection always ends in a close event.
    socket.onclose = lose
  }, 0)

  return {
    send(message) {
      if (done) return
      const sent = transmit(message)
      if (message.type !== 'session.end') return
      if (!sent) lose()
      else endTimer ??= window.setTimeout(lose, END_TIMEOUT_MS)
    },
    close() {
      if (done) return
      transmit({ type: 'session.end' })
      finish()
    },
  }
}
