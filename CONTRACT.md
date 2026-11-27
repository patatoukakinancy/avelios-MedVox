# Contract: Backend <-> Frontend

## Rule
Frontend only ever sees `public_card`. Hidden clinical facts never leave the backend.

## public_card
{ "display_name": str, "age": int, "sex": "female|male", "setting": str, "presenting_complaint": str, "difficulty": "easy|medium|hard", "estimated_minutes": int }

Source of this shape: `public_card` in `schema/patient_case.schema.json`.

## REST (implemented)
- GET /patients -> [{"patient_id": str, "public_card": {...}}], sorted by patient_id, public data only

## WebSocket  /ws/session?patient_id=<id>&mode=voice|text
Audio format: PCM16, 24 kHz, mono, base64 inside JSON.

Client -> server
- {"type":"audio.append","audio":"<base64>"}   voice mode; only send while the mic is actively in use (silence costs money)
- {"type":"text.send","text":"..."}
- {"type":"interrupt","played_ms":int}         send when the user barges in: how many ms of the current patient audio was actually played
- {"type":"session.end"}

Server -> client
- {"type":"session.ready","patient_public":{...public_card...}}
- {"type":"speech.started"}                    STOP audio playback immediately and clear the queue
- {"type":"audio.delta","audio":"<base64>"}
- {"type":"transcript.delta","role":"user|patient","item_id":str,"text":str}
- {"type":"transcript.final","role":"user|patient","item_id":str,"text":str}
- {"type":"latency","turn":int,"ttfa_ms":int|null,"ttft_ms":int|null}
- {"type":"error","code":str,"message":str}   codes so far: busy, bad_message, upstream_closed, not_found, budget_exhausted
- {"type":"session.ended","reason":"client|timeout|idle|budget|error","turns":int,"usage":{...}}

The patient never speaks first. The first patient audio/text arrives only after the student's first message.

Only one session can be active at a time. Max session length is set by the backend.

## Planned (shapes to be agreed before implementation)
- POST /evaluate        -> structured history + rubric checklist
- POST /generate-case   -> new patient JSON from a clinical vignette