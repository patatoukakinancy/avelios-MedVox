// Mirrors ../../CONTRACT.md. Change the contract first, then this file.

export interface PublicCard {
  display_name: string
  age: number
  sex: 'female' | 'male'
  setting: string
  presenting_complaint: string
  difficulty: 'easy' | 'medium' | 'hard'
  estimated_minutes: number
}

export interface PatientSummary {
  patient_id: string
  public_card: PublicCard
}

export type Role = 'user' | 'patient'

export type ClientMessage =
  | { type: 'audio.append'; audio: string }
  | { type: 'text.send'; text: string }
  | { type: 'interrupt'; played_ms: number }
  | { type: 'session.end' }

export type ServerMessage =
  | { type: 'session.ready'; patient_public: PublicCard }
  | { type: 'speech.started' }
  | { type: 'audio.delta'; audio: string }
  | { type: 'transcript.delta'; role: Role; item_id: string; text: string }
  | { type: 'transcript.final'; role: Role; item_id: string; text: string }
  | { type: 'latency'; turn: number; ttfa_ms: number | null; ttft_ms: number | null }
  | { type: 'error'; code: string; message: string }
  | {
      type: 'session.ended'
      reason: 'client' | 'timeout' | 'idle' | 'budget' | 'error'
      turns: number
      usage: Record<string, unknown>
    }
