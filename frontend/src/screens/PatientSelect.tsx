import { useEffect, useState } from 'react'
import { listPatients } from '../api/patients'
import { Avatar } from '../components/Avatar'
import type { PatientSummary } from '../protocol'

interface Props {
  onStart: (patient: PatientSummary) => void
}

export function PatientSelect({ onStart }: Props) {
  const [patients, setPatients] = useState<PatientSummary[]>([])

  useEffect(() => {
    listPatients().then(setPatients)
  }, [])

  return (
    <main>
      <header className="intro">
        <p className="brand">MedVox</p>
        <h1>Choose a patient</h1>
        <p className="muted">Practise history-taking with a virtual patient.</p>
      </header>
      <ul className="cards">
        {patients.map((patient) => {
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
