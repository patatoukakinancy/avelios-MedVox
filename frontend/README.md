# MedVox frontend

React + TypeScript + Vite. The patient list comes from the backend (`GET /patients`).
The consultation can be Voice or Text (chosen before it starts; Voice is the default, see `DEFAULT_MODE`
in `src/App.tsx`). It talks to the real backend by default, **which uses the OpenAI API and costs money**.
Use `?transport=mock` for UI work.

## Voice mode

- Chrome or Edge, and preferably wired headphones.
- Audio is sent only while the microphone is on. Turning it off sends 1 s of silence first, so the
  server notices that the question has ended.
- With the mock, your own speech is played back to you (a rough volume-based stand-in for the backend).
- Talking over the patient stops playback and sends `interrupt` with `played_ms`. Audio arriving in the
  next 400 ms is dropped; this relies on the backend's `VAD_SILENCE_MS` being at least 400.
- If the server opens a text session instead (`session.ready.mode`), the UI switches to text.

## Mock or real consultation

- `http://localhost:5173/` connects to the backend (`/ws/session`).
- `http://localhost:5173/?transport=mock` uses the fake patient (the patient list still comes from the backend).
- The default is `DEFAULT_TRANSPORT` in `src/session/selectTransport.ts`.

In dev builds, every server message is logged with `console.debug` (enable "Verbose" in the browser console).

## Commands

```
npm install
npm run dev     # http://localhost:5173
npm run build   # type-check + production build
npm run lint
```

- The backend must be running on port 8000 (see `backend/README.md`). In dev, Vite proxies `/patients` and `/ws` to it.
- WS and API shapes: `../CONTRACT.md` (mirrored in `src/protocol.ts`).
- Only `public_card` data belongs here. Never import from `../cases/`.
