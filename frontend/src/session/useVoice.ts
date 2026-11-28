import { useCallback, useRef, useState } from 'react'
import { createAudioPlayer } from '../audio/audioPlayer'
import { startMicCapture, type MicCapture } from '../audio/micCapture'
import { floatToPcm16Base64 } from '../audio/pcm'
import type { ClientMessage } from '../protocol'
import type { SessionEvent } from './transport'

export type MicState = 'off' | 'starting' | 'on'

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
    try {
      const mic = await startMicCapture(
        (samples) => {
          if (isCurrent()) send({ type: 'audio.append', audio: floatToPcm16Base64(samples) })
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
  }, [send, stopMic])

  const shutdown = useCallback(() => {
    stopMic()
    player.close()
  }, [player, stopMic])

  const handleEvent = useCallback(
    (event: SessionEvent) => {
      if (event.type === 'audio.delta') player.enqueue(event.audio)
      if (event.type === 'speech.started') player.stop()
      if (event.type === 'session.ended' || event.type === 'connection.lost') shutdown()
    },
    [player, shutdown],
  )

  return { micState, micError, patientSpeaking, startMic, stopMic, shutdown, handleEvent }
}
