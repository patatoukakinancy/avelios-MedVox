import { useCallback, useRef, useState } from 'react'
import { createAudioPlayer } from '../audio/audioPlayer'
import { startMicCapture, type MicCapture } from '../audio/micCapture'
import { floatToPcm16Base64, rms, SAMPLE_RATE } from '../audio/pcm'
import type { ClientMessage } from '../protocol'
import type { SessionEvent } from './transport'

export type MicState = 'off' | 'starting' | 'on'

// After a barge-in, audio of the interrupted reply may still be on its way. The next reply
// cannot start this soon, because the server first waits for silence (VAD_SILENCE_MS, 500).
const STALE_AUDIO_MS = 400

// 1 s of silence in 40 ms chunks, so the server hears that the question has ended.
const SILENT_CHUNK = floatToPcm16Base64(new Float32Array(SAMPLE_RATE * 0.04))
const SILENT_CHUNKS = 25

// A mic level older than this is ignored (chunks arrive every 40 ms).
const MIC_LEVEL_MAX_AGE_MS = 150

function describeMicError(error: unknown) {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError')
    return 'Microphone access was blocked. Allow it in the browser, or start a text consultation.'
  if (name === 'NotFoundError') return 'No microphone was found.'
  if (name === 'NotSupportedError')
    return 'Voice mode is not supported in this browser. Use Chrome or Edge, or start a text consultation.'
  return 'Could not start the microphone. You can start a text consultation instead.'
}

// Microphone and playback. Audio itself never goes into React state.
export function useVoice(send: (message: ClientMessage) => void) {
  const [micState, setMicState] = useState<MicState>('off')
  const [micError, setMicError] = useState<string | null>(null)
  const [patientSpeaking, setPatientSpeaking] = useState(false)
  const [player] = useState(() => createAudioPlayer(setPatientSpeaking))
  const micRef = useRef<MicCapture | null>(null)
  // Changes on every start and stop, so that a late permission answer is discarded.
  const requestRef = useRef(0)
  const ignoreAudioUntilRef = useRef(0)
  const micLevelRef = useRef({ value: 0, at: 0 })

  const stopMic = useCallback(() => {
    requestRef.current += 1
    micRef.current?.stop()
    micRef.current = null
    setMicState('off')
  }, [])

  const startMic = useCallback(async () => {
    const request = ++requestRef.current
    const isCurrent = () => request === requestRef.current
    setMicError(null)
    setMicState('starting')
    player.prepare()
    try {
      const mic = await startMicCapture(
        (samples) => {
          if (!isCurrent()) return
          micLevelRef.current = { value: rms(samples), at: performance.now() }
          send({ type: 'audio.append', audio: floatToPcm16Base64(samples) })
        },
        () => {
          if (isCurrent()) stopMic()
        },
      )
      if (!isCurrent()) {
        mic.stop()
        return
      }
      micRef.current = mic
      setMicState('on')
    } catch (error) {
      if (!isCurrent()) return
      console.warn('[mic]', error)
      setMicError(describeMicError(error))
      setMicState('off')
    }
  }, [player, send, stopMic])

  // The student's own "microphone off". Ending the session uses shutdown() instead.
  const turnMicOff = useCallback(() => {
    if (micRef.current) {
      for (let i = 0; i < SILENT_CHUNKS; i++) send({ type: 'audio.append', audio: SILENT_CHUNK })
    }
    stopMic()
  }, [send, stopMic])

  const shutdown = useCallback(() => {
    stopMic()
    player.close()
  }, [player, stopMic])

  const handleEvent = useCallback(
    (event: SessionEvent) => {
      if (event.type === 'audio.delta' && performance.now() >= ignoreAudioUntilRef.current) {
        player.enqueue(event.audio)
      }
      if (event.type === 'speech.started') {
        const bargedIn = player.isPlaying()
        // Read before stop(), which resets the count for the next reply.
        const playedMs = player.playedMs()
        player.stop()
        if (bargedIn) {
          ignoreAudioUntilRef.current = performance.now() + STALE_AUDIO_MS
          send({ type: 'interrupt', played_ms: playedMs })
        }
      }
      if (event.type === 'session.ended' || event.type === 'connection.lost') shutdown()
    },
    [player, send, shutdown],
  )

  // Current loudness of each side. Polled every animation frame, so not React state.
  const getLevels = useCallback(() => {
    const { value, at } = micLevelRef.current
    const fresh = micRef.current !== null && performance.now() - at < MIC_LEVEL_MAX_AGE_MS
    return { student: fresh ? value : 0, patient: player.level() }
  }, [player])

  return { micState, micError, patientSpeaking, startMic, turnMicOff, shutdown, handleEvent, getLevels }
}
