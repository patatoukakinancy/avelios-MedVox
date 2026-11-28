# MedVox frontend

React + TypeScript + Vite. The patient list comes from the backend (`GET /patients`).
The consultation is text mode only and uses a mock session by default.

## Mock or real consultation

- `http://localhost:5173/?transport=ws` connects to the backend (`/ws/session`).
- `http://localhost:5173/?transport=mock` uses the fake patient.
- Without the parameter, `DEFAULT_TRANSPORT` in `src/session/selectTransport.ts` applies.

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
