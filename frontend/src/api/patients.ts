import type { PatientSummary } from '../protocol'

// GET /patients returns public cards only. In dev, Vite proxies it to the backend.
export async function listPatients(): Promise<PatientSummary[]> {
  const response = await fetch('/patients')
  if (!response.ok) throw new Error(`GET /patients failed with status ${response.status}`)
  return response.json()
}
