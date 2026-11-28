import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { ClientMessage, PatientSummary, SessionMode } from '../protocol'
import { openTransport } from './selectTransport'
import { initialState, sessionReducer } from './sessionReducer'
import type { Transport } from './transport'
import { useVoice } from './useVoice'

// One hook instance is one session: remount the component to start a new one.
export function useSession(patient: PatientSummary, mode: SessionMode) {
  const [state, dispatch] = useReducer(sessionReducer, initialState)
  const transportRef = useRef<Transport | null>(null)
  const sentCount = useRef(0)

  const send = useCallback((message: ClientMessage) => transportRef.current?.send(message), [])
  const voice = useVoice(send)
  const { handleEvent, shutdown } = voice

  useEffect(() => {
    const transport = openTransport(patient, mode, (event) => {
      handleEvent(event)
      if (event.type === 'speech.started') dispatch({ type: event.type, at: performance.now() })
      else if (event.type !== 'audio.delta') dispatch(event)
    })
    transportRef.current = transport
    return () => {
      shutdown()
      transport.close()
    }
  }, [patient, mode, handleEvent, shutdown])

  return {
    ...state,
    voice,
    sendText: (text: string) => {
      sentCount.current += 1
      dispatch({ type: 'local.sent', item_id: `local_${sentCount.current}`, text })
      send({ type: 'text.send', text })
    },
    endSession: () => {
      // Stop the microphone and playback right away, without waiting for the server.
      shutdown()
      send({ type: 'session.end' })
    },
  }
}
