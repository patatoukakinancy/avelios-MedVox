import { useState } from 'react'
import type { PatientSummary, SessionMode } from './protocol'
import { Consultation } from './screens/Consultation'
import { PatientSelect } from './screens/PatientSelect'

// The student can switch to Text before starting a consultation.
const DEFAULT_MODE: SessionMode = 'voice'

export default function App() {
  const [patient, setPatient] = useState<PatientSummary | null>(null)
  const [mode, setMode] = useState<SessionMode>(DEFAULT_MODE)

  if (!patient) return <PatientSelect mode={mode} onModeChange={setMode} onStart={setPatient} />
  return <Consultation patient={patient} mode={mode} onExit={() => setPatient(null)} />
}
