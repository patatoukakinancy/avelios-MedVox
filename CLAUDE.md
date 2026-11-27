# Project: Standardized Patient Voice Simulator (hackathon, 36h)

Voice patient for medical students to practise history-taking in English. A working patient beats a polished deck. Judged on: naturalness/latency, medical consistency, distinct personality, working demo.

## Layout
- backend/   Python/FastAPI (owner: backend dev)
- frontend/  owner: frontend dev
- cases/     shared Patient JSON files, one per patient (cases/{patient_id}.json, e.g. case_01); schema in schema/
- CONTRACT.md  the single source of truth for the WS protocol and API shapes. Never change it unilaterally: if code needs a change, update CONTRACT.md in the same change and flag it.

## Shared rules
- NEVER read, print, log or commit any .env file or API key. The OpenAI key lives only in backend/.env and only the backend uses it.
- The frontend receives ONLY a patient's public_card. Hidden clinical facts never leave the backend.
- Stay in your own folder. Do not edit the other person's folder unless explicitly asked.
- Scope is strict: no login, no database, no multi-specialty features. Do not add features that were not requested in the current prompt.
- Small verifiable steps; run the verification command after each task and report the result.