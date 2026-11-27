import type { PatientSummary } from '../protocol'

// Mock until GET /patients exists (still "Planned" in CONTRACT.md, so the
// { patient_id, public_card } shape is an assumption).
// Public card values are copied by hand on purpose: never import from cases/,
// those files contain hidden clinical facts.
const MOCK_PATIENTS: PatientSummary[] = [
  {
    patient_id: 'case_01',
    public_card: {
      display_name: 'Robert Hayes',
      age: 58,
      sex: 'male',
      setting: 'GP clinic',
      presenting_complaint: 'Chest discomfort',
      difficulty: 'medium',
      estimated_minutes: 10,
    },
  },
  {
    patient_id: 'case_02',
    public_card: {
      display_name: 'Margaret Collins',
      age: 67,
      sex: 'female',
      setting: 'GP clinic',
      presenting_complaint: 'Tiredness and getting out of breath',
      difficulty: 'hard',
      estimated_minutes: 12,
    },
  },
]

export function listPatients(): Promise<PatientSummary[]> {
  return Promise.resolve(MOCK_PATIENTS)
}
