import { useEffect, useRef, type ReactNode, type Ref } from 'react'
import type { PublicCard } from '../protocol'
import type { useVoice } from '../session/useVoice'
import { PatientAvatar } from './PatientAvatar'

// Mic loudness (RMS) that counts as the student talking. Raise it if room noise lights the circle.
const STUDENT_SPEECH_RMS = 0.04
// Keeps a wave on through the short pauses between words.
const HOLD_MS = 300
// RMS drawn at full strength.
const FULL_RMS = 0.25
// Relative heights of the bars between the two circles.
const BARS = [0.45, 0.7, 1, 0.8, 0.9, 0.65, 0.4]

// 0 to 1, with a boost for quiet speech.
const strength = (value: number) => Math.min(1, Math.sqrt(value / FULL_RMS))

// Rise quickly and fall slowly, so that the movement is smooth.
const ease = (from: number, to: number) => from + (to - from) * (to > from ? 0.3 : 0.08)

interface Props {
  voice: ReturnType<typeof useVoice>
  live: boolean
  sex: PublicCard['sex']
  hint: string | null
}

// The voice consultation as a call: who is talking, instead of what is being said.
// The text status for screen readers is in VoiceControls.
export function CallStage({ voice, live, sex, hint }: Props) {
  const { getLevels, patientSpeaking } = voice
  const studentRef = useRef<HTMLDivElement>(null)
  const patientRef = useRef<HTMLDivElement>(null)
  const waveRef = useRef<HTMLDivElement>(null)
  const patientSpeakingRef = useRef(patientSpeaking)

  useEffect(() => {
    patientSpeakingRef.current = patientSpeaking
  }, [patientSpeaking])

  // Writes straight to the DOM: React does not re-render 60 times a second.
  useEffect(() => {
    let frame = 0
    let studentUntil = 0
    let patientUntil = 0
    let studentLevel = 0
    let patientLevel = 0

    function draw(now: number) {
      const levels = getLevels()
      // While the patient talks, the mic mostly hears echo. A real interruption stops the
      // patient's audio (speech.started), and then the student's wave takes over.
      if (patientSpeakingRef.current) {
        patientUntil = now + HOLD_MS
        studentUntil = 0
      } else if (levels.student >= STUDENT_SPEECH_RMS) {
        studentUntil = now + HOLD_MS
        patientUntil = 0
      }
      const studentSpeaking = now < studentUntil
      const patientTalking = now < patientUntil

      studentLevel = ease(studentLevel, studentSpeaking ? strength(levels.student) : 0)
      patientLevel = ease(patientLevel, patientTalking ? strength(levels.patient) : 0)
      show(studentRef.current, studentSpeaking, studentLevel)
      show(patientRef.current, patientTalking, patientLevel)

      const wave = waveRef.current
      if (wave) {
        const level = Math.max(studentLevel, patientLevel)
        wave.dataset.speaking = String(studentSpeaking || patientTalking)
        BARS.forEach((height, i) => {
          const ripple = 0.65 + 0.35 * Math.sin(now / 110 + i * 1.4)
          const bar = wave.children[i] as HTMLElement
          bar.style.setProperty('--bar', String(0.14 + 0.86 * level * height * ripple))
        })
      }
      frame = requestAnimationFrame(draw)
    }

    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [getLevels])

  return (
    <section className="call-stage" aria-label="Voice consultation">
      {live && <span className="live">Live</span>}
      <div className="call-row">
        <Participant ref={studentRef} label="Student">
          <Stethoscope />
        </Participant>
        <div className="call-wave" ref={waveRef} aria-hidden="true">
          {BARS.map((_, i) => (
            <span key={i} />
          ))}
        </div>
        <Participant ref={patientRef} label="Virtual patient">
          <PatientAvatar sex={sex} />
        </Participant>
      </div>
      {hint && <p className="call-hint">{hint}</p>}
    </section>
  )
}

function show(element: HTMLElement | null, speaking: boolean, level: number) {
  if (!element) return
  element.dataset.speaking = String(speaking)
  element.style.setProperty('--level', level.toFixed(3))
}

function Participant({ ref, label, children }: { ref: Ref<HTMLDivElement>; label: string; children: ReactNode }) {
  return (
    <div className="participant" ref={ref}>
      <div className="orb" aria-hidden="true">
        <div className="orb-waves">
          <span className="halo" />
          <span className="ring" />
          <span className="ring" />
          <span className="ring" />
        </div>
        <div className="orb-face">{children}</div>
      </div>
      <span className="participant-label">{label}</span>
    </div>
  )
}

function Stethoscope() {
  return (
    <svg className="stethoscope" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 3H4v5a5 5 0 0 0 10 0V3h-2" />
      <path d="M9 13v2.500a5.250 5.250 0 0 0 10.500 0V13" />
      <circle cx="19.500" cy="10.500" r="2.500" />
    </svg>
  )
}
