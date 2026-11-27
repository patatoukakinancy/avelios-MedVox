import { useState } from 'react'
import type { PatientSummary } from './protocol'
import { Consultation } from './screens/Consultation'
import { PatientSelect } from './screens/PatientSelect'

export default function App() {
  const [patient, setPatient] = useState<PatientSummary | null>(null)

  if (!patient) return <PatientSelect onStart={setPatient} />
  return <Consultation patient={patient} onExit={() => setPatient(null)} />
}
