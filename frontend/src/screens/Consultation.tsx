import { useState, type SubmitEvent } from 'react'
import { Avatar } from '../components/Avatar'
import type { PatientSummary } from '../protocol'
import { transportKind } from '../session/selectTransport'
import { useSession } from '../session/useSession'

interface Props {
  patient: PatientSummary
  onExit: () => void
}

export function Consultation({ patient, onExit }: Props) {
  const session = useSession(patient)
  const [draft, setDraft] = useState('')

  const card = session.card ?? patient.public_card
  const ready = session.status === 'ready'

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!ready || !text) return
    session.sendText(text)
    setDraft('')
  }

  return (
    <main className="consultation">
      <header>
        <div className="identity">
          <Avatar name={card.display_name} />
          <div>
            <h1>{card.display_name}</h1>
            <p className="muted">
              {card.setting} · {card.presenting_complaint}
            </p>
            {transportKind === 'mock' && <span className="badge mock">Mock session</span>}
          </div>
        </div>
        {ready ? (
          <button className="danger" onClick={session.endSession}>
            End consultation
          </button>
        ) : (
          <button className="secondary" onClick={onExit}>
            Back to patients
          </button>
        )}
      </header>

      <ol className="transcript" aria-live="polite">
        {ready && session.transcript.length === 0 && (
          <li className="empty">Greet your patient to begin.</li>
        )}
        {session.transcript.map((item) => (
          <li key={item.item_id} className={item.role}>
            <span className="speaker">{item.role === 'user' ? 'You' : 'Patient'}</span>
            {item.text}
          </li>
        ))}
      </ol>

      {session.status === 'connecting' && <p className="muted">Connecting…</p>}
      {session.status === 'ended' && <p className="muted">Session ended ({session.endedReason}).</p>}
      {session.error && <p role="alert">{session.error}</p>}

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type a question…"
          aria-label="Your question"
          disabled={!ready}
        />
        <button type="submit" disabled={!ready || !draft.trim()}>
          Send
        </button>
      </form>
    </main>
  )
}
