# MedVox frontend

React + TypeScript + Vite. The patient list comes from the backend (`GET /patients`).
The consultation is still text mode against a mock session.

```
npm install
npm run dev     # http://localhost:5173
npm run build   # type-check + production build
npm run lint
```

- The backend must be running on port 8000 (see `backend/README.md`). In dev, Vite proxies `/patients` to it.
- WS and API shapes: `../CONTRACT.md` (mirrored in `src/protocol.ts`).
- Only `public_card` data belongs here. Never import from `../cases/`.
