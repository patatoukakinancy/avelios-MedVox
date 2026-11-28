# Backend

## Setup (PowerShell, from backend/)
1. `python -m venv .venv`
2. `.\.venv\Scripts\Activate.ps1`
3. `pip install -r requirements.txt`
4. Copy the keys from the root `.env.example` into `backend/.env` and fill in the values. Never commit `.env`.
   - Required: `OPENAI_API_KEY`, `REALTIME_MODEL` (for example `gpt-realtime-2.1` or `gpt-realtime-2.1-mini`).
   - Recommended: `TRANSCRIBE_MODEL=gpt-4o-mini-transcribe`. Without it there are no user transcripts in voice mode.
   - Optional, with defaults:
     - `MAX_SESSION_SECONDS=720`
     - `IDLE_TIMEOUT_SECONDS=90`
     - `MAX_OUTPUT_TOKENS=150`
     - `VAD_THRESHOLD=0.5` (raise it for noisy rooms)
     - `VAD_SILENCE_MS=500`
     - `VAD_PREFIX_PADDING_MS=300`
     - `REASONING_EFFORT=minimal`. Set it to `none` to omit reasoning.
     - `CORS_ORIGINS`: comma-separated allowed origins for the REST routes (`GET /patients`). Empty or unset means `http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000`. A wildcard `*` is ignored.
5. `python scripts/check_env.py` prints only whether each key is set, never its value.
6. `python -m pytest -q` runs offline against a fake upstream.

## Run
- `uvicorn app.main:app --reload`
- REST: `GET /patients`
- WebSocket: `/ws/session?patient_id=case_01&mode=voice|text`. The protocol is in `../CONTRACT.md`.

## Smoke test (second window, server running)
- `python scripts/ws_smoke_test.py --patient case_01 --text "Hi, I'm the medical student. What brings you in today?"`
- Several turns in one session: repeat `--text`. Each turn appends a line to `backend/logs/latency.jsonl`.
- Busy check: start one smoke test with `--hold 20`, then start a second one while it runs. The second gets `error busy`.
- Every latency line shows `vad_silence_ms`. For voice turns, perceived latency = `ttfa_ms + vad_silence_ms`.

## Session behaviour
- Only one session can be active at a time.
- The session ends on whichever comes first:
  - `MAX_SESSION_SECONDS` passes (reason `timeout`).
  - `IDLE_TIMEOUT_SECONDS` passes without `text.send`, `interrupt` or detected speech (reason `idle`). `audio.append` alone does not count as activity.
- If voice setup fails, the backend retries in this order:
  1. Voice config.
  2. Voice config without reasoning.
  3. Text config.
  4. If all fail, the client gets `error upstream_closed`.

  `session.ready.mode` says which mode applies.
