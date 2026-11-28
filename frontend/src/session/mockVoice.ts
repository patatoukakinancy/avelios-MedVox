// Fake voice-mode server: detects speech by volume and plays your own words back.
// A rough stand-in for the backend's speech detection, for local testing only.
import { pcm16Base64ToFloat } from '../audio/pcm'
import type { PatientSummary, ServerMessage } from '../protocol'
import type { SessionEvent, Transport } from './transport'

const SPEECH_RMS = 0.02 // raise it if background noise triggers the mock
const ONSET_CHUNKS = 2 // consecutive loud chunks that count as speech
const PRE_ROLL_CHUNKS = 5 // audio kept from just before the onset
const SILENCE_CHUNKS = 18 // about 700 ms of 40 ms chunks
const NO_AUDIO_MS = 700 // no chunks at all: the microphone was turned off
const MAX_CHUNKS = 375 // about 15 s

function rms(base64: string) {
  const samples = pcm16Base64ToFloat(base64)
  return Math.sqrt(samples.reduce((sum, s) => sum + s * s, 0) / (samples.length || 1))
}

export function openMockVoiceTransport(
  patient: PatientSummary,
  onEvent: (event: SessionEvent) => void,
): Transport {
  const timers = new Set<number>()
  let idleTimer: number | undefined
  let recent: string[] = []
  let utterance: string[] | null = null
  let loud = 0
  let quiet = 0
  let turns = 0
  let ended = false

  function emit(message: ServerMessage, delayMs = 0) {
    const timer = window.setTimeout(() => {
      timers.delete(timer)
      onEvent(message)
    }, delayMs)
    timers.add(timer)
  }

  function clearTimers() {
    timers.forEach((timer) => window.clearTimeout(timer))
    timers.clear()
    window.clearTimeout(idleTimer)
  }

  function reply() {
    window.clearTimeout(idleTimer)
    if (!utterance) return
    // Drop most of the trailing silence.
    const chunks = utterance.slice(0, Math.max(1, utterance.length - Math.max(0, quiet - 5)))
    utterance = null
    recent = []
    loud = 0
    quiet = 0
    turns += 1
    emit({ type: 'transcript.final', role: 'user', item_id: `user_${turns}`, text: '[mock] (your speech)' })
    const item_id = `patient_${turns}`
    const text = '[mock reply] Playing back what you said.'
    emit({ type: 'transcript.delta', role: 'patient', item_id, text }, 100)
    chunks.forEach((audio, i) => emit({ type: 'audio.delta', audio }, 100 + i * 10))
    emit({ type: 'transcript.final', role: 'patient', item_id, text }, 100 + chunks.length * 10)
  }

  function listen(audio: string) {
    const isLoud = rms(audio) >= SPEECH_RMS
    if (!utterance) {
      recent = [...recent.slice(-(PRE_ROLL_CHUNKS - 1)), audio]
      loud = isLoud ? loud + 1 : 0
      if (loud < ONSET_CHUNKS) return
      // New speech: cancel whatever the fake patient was still sending.
      clearTimers()
      utterance = [...recent]
      quiet = 0
      emit({ type: 'speech.started' })
    } else {
      utterance.push(audio)
      quiet = isLoud ? 0 : quiet + 1
    }
    window.clearTimeout(idleTimer)
    if (quiet >= SILENCE_CHUNKS || utterance.length >= MAX_CHUNKS) reply()
    else idleTimer = window.setTimeout(reply, NO_AUDIO_MS)
  }

  emit({ type: 'session.ready', patient_public: patient.public_card, mode: 'voice' }, 300)

  return {
    send(message) {
      if (ended) return
      if (message.type === 'audio.append') listen(message.audio)
      if (message.type === 'session.end') {
        ended = true
        clearTimers()
        emit({ type: 'session.ended', reason: 'client', turns, usage: {} })
      }
    },
    close() {
      ended = true
      clearTimers()
    },
  }
}
