import { useEffect, useState } from 'react'
import { listPatients } from '../api/patients'
import { Avatar } from '../components/Avatar'
import type { PatientSummary } from '../protocol'

interface Props {
  onStart: (patient: PatientSummary) => void
}

export function PatientSelect({ onStart }: Props) {
  // null while loading
  const [patients, setPatients] = useState<PatientSummary[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    listPatients()
      .then(setPatients)
      .catch((error) => {
        console.error(error)
        setFailed(true)
      })
  }, [])

  return (
    <main>
      <header className="intro">
        <p className="brand">MedVox</p>
        <h1>Choose a patient</h1>
        <p className="muted">Practise history-taking with a virtual patient.</p>
      </header>
      {failed && (
        <p role="alert">Could not load patients. Check that the backend is running, then reload the page.</p>
      )}
      {!failed && patients === null && <p className="muted">Loading patients…</p>}
      <ul className="cards">
        {patients?.map((patient) => {
          const card = patient.public_card
          return (
            <li key={patient.patient_id} className="card">
              <div className="identity">
                <Avatar name={card.display_name} />
                <div>
                  <h2>{card.display_name}</h2>
                  <p className="muted">
                    {card.age}, {card.sex} · {card.setting}
                  </p>
                </div>
              </div>
              <p className="complaint">{card.presenting_complaint}</p>
              <div className="meta">
                <span className={`badge ${card.difficulty}`}>{card.difficulty}</span>
                <span className="muted">about {card.estimated_minutes} min</span>
              </div>
              <button onClick={() => onStart(patient)}>Start consultation</button>
            </li>
          )
        })}
      </ul>
    </main>
  )
}
