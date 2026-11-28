import { useState } from 'react'
import type { PatientSummary, SessionMode } from './protocol'
import { Consultation } from './screens/Consultation'
import { PatientSelect } from './screens/PatientSelect'

// Switch to 'voice' once voice mode works with the real backend.
const DEFAULT_MODE: SessionMode = 'text'

export default function App() {
  const [patient, setPatient] = useState<PatientSummary | null>(null)
  const [mode, setMode] = useState<SessionMode>(DEFAULT_MODE)

  if (!patient) return <PatientSelect mode={mode} onModeChange={setMode} onStart={setPatient} />
  return <Consultation patient={patient} mode={mode} onExit={() => setPatient(null)} />
}
