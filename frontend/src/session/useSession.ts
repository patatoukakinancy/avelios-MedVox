import { useEffect, useReducer, useRef } from 'react'
import type { PatientSummary } from '../protocol'
import { openTransport } from './selectTransport'
import { initialState, sessionReducer } from './sessionReducer'
import type { Transport } from './transport'

// One hook instance is one session: remount the component to start a new one.
export function useSession(patient: PatientSummary) {
  const [state, dispatch] = useReducer(sessionReducer, initialState)
  const transportRef = useRef<Transport | null>(null)
  const sentCount = useRef(0)

  useEffect(() => {
    const transport = openTransport(patient, dispatch)
    transportRef.current = transport
    return () => transport.close()
  }, [patient])

  return {
    ...state,
    sendText: (text: string) => {
      sentCount.current += 1
      dispatch({ type: 'local.sent', item_id: `local_${sentCount.current}`, text })
      transportRef.current?.send({ type: 'text.send', text })
    },
    endSession: () => transportRef.current?.send({ type: 'session.end' }),
  }
}
