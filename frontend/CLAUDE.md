# Frontend rules (React, TypeScript, Vite)

## Commands (from frontend/)
- Run:    npm run dev
- Checks: npm run build; npm run lint

## API cost (the OpenAI key is the sponsor's: do not waste it)
- The plain address `http://localhost:5173/` talks to the real backend and **costs money**.
- For UI and styling work, and any check that does not need the real patient, use
  `http://localhost:5173/?transport=mock`. This also applies to browser automation: always set the
  `transport` parameter explicitly, or point the dev server at a fake backend.
- Before anything that would call the real API (a real consultation, a smoke test against the real
  backend), ask the user first.
- When a real test is needed, keep it short: prefer Text, turn the microphone off when not speaking
  (silence costs money too), and press "End consultation" when done.
- Do not change the cost safeguards (audio only while the microphone is on) without asking.
