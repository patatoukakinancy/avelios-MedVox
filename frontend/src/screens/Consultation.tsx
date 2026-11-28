import { useLayoutEffect, useRef, useState, type SubmitEvent, type UIEvent } from 'react'
import { Avatar } from '../components/Avatar'
import { VoiceControls } from '../components/VoiceControls'
import type { PatientSummary, SessionMode } from '../protocol'
import { transportKind } from '../session/selectTransport'
import { useSession } from '../session/useSession'

interface Props {
  patient: PatientSummary
  mode: SessionMode
  onExit: () => void
}

export function Consultation({ patient, mode, onExit }: Props) {
  const session = useSession(patient, mode)
  const [draft, setDraft] = useState('')

  const card = session.card ?? patient.public_card
  const ready = session.status === 'ready'

  const transcriptRef = useRef<HTMLOListElement>(null)
  // Follow new messages unless the student has scrolled up to read earlier ones.
  const followRef = useRef(true)

  // Runs after every render: status messages below the list also change its height.
  useLayoutEffect(() => {
    const list = transcriptRef.current
    if (list && followRef.current) list.scrollTop = list.scrollHeight
  })

  function handleScroll(event: UIEvent<HTMLOListElement>) {
    const { scrollHeight, scrollTop, clientHeight } = event.currentTarget
    followRef.current = scrollHeight - scrollTop - clientHeight < 40
  }

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!ready || !text) return
    followRef.current = true
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

      <ol className="transcript" aria-live="polite" ref={transcriptRef} onScroll={handleScroll}>
        {ready && session.transcript.length === 0 && (
          <li className="empty">
            {mode === 'voice' ? 'Turn on the microphone and greet your patient to begin.' : 'Greet your patient to begin.'}
          </li>
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

      {mode === 'voice' ? (
        <VoiceControls voice={session.voice} ready={ready} />
      ) : (
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
      )}
    </main>
  )
}
