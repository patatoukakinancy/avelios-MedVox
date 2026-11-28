import type { useVoice } from '../session/useVoice'

interface Props {
  voice: ReturnType<typeof useVoice>
  ready: boolean
}

export function VoiceControls({ voice, ready }: Props) {
  const { micState, micError, patientSpeaking, startMic, stopMic } = voice
  const status = patientSpeaking
    ? 'Patient is speaking'
    : { off: 'Microphone off', starting: 'Starting microphone…', on: 'Listening' }[micState]

  return (
    <div>
      {micError && <p role="alert">{micError}</p>}
      <div className="voice-bar">
        <button
          type="button"
          className={micState === 'on' ? 'danger' : undefined}
          onClick={micState === 'on' ? stopMic : startMic}
          disabled={!ready || micState === 'starting'}
        >
          {micState === 'on' ? 'Turn microphone off' : 'Turn microphone on'}
        </button>
        <span className="muted" role="status">
          {status}
        </span>
      </div>
      <p className="muted">Use headphones, so the patient's voice does not reach the microphone.</p>
    </div>
  )
}
