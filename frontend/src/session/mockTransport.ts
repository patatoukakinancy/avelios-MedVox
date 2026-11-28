import type { ServerMessage } from '../protocol'
import { openMockVoiceTransport } from './mockVoice'
import type { OpenTransport } from './transport'

// Fake server. Replies are placeholders with no clinical content.
export const openMockTransport: OpenTransport = (patient, mode, onMessage) => {
  if (mode === 'voice') return openMockVoiceTransport(patient, onMessage)

  const timers = new Set<number>()
  let turns = 0
  let ended = false

  function emit(message: ServerMessage, delayMs: number) {
    const timer = window.setTimeout(() => {
      timers.delete(timer)
      onMessage(message)
    }, delayMs)
    timers.add(timer)
  }

  function clearTimers() {
    timers.forEach((timer) => window.clearTimeout(timer))
    timers.clear()
  }

  emit({ type: 'session.ready', patient_public: patient.public_card, mode: 'text' }, 300)

  return {
    send(message) {
      if (ended) return

      if (message.type === 'text.send') {
        turns += 1
        emit({ type: 'transcript.final', role: 'user', item_id: `user_${turns}`, text: message.text }, 0)

        const item_id = `patient_${turns}`
        const chunks = ['[mock reply] ', 'This is a placeholder ', `answer to question ${turns}.`]
        chunks.forEach((text, i) => {
          emit({ type: 'transcript.delta', role: 'patient', item_id, text }, 400 + i * 200)
        })
        emit({ type: 'transcript.final', role: 'patient', item_id, text: chunks.join('') }, 400 + chunks.length * 200)
        emit({ type: 'latency', turn: turns, ttfa_ms: null, ttft_ms: 400 }, 400 + chunks.length * 200)
      }

      if (message.type === 'session.end') {
        ended = true
        clearTimers()
        emit({ type: 'session.ended', reason: 'client', turns, usage: {} }, 0)
      }
    },
    close() {
      ended = true
      clearTimers()
    },
  }
}
