import logging

from fastapi import FastAPI, WebSocket

from . import session as session_mod
from .cases import CaseNotFound, InvalidPatientId, list_patients, load_case
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Standardized Patient Voice Simulator")

# Injection points for tests (fake upstream, test settings). No network in tests.
settings_provider = get_settings
upstream_connect = session_mod.default_connect


@app.get("/patients")
def get_patients() -> list[dict]:
    """[{patient_id, public_card}] only. Hidden clinical data never leaves the backend."""
    return list_patients()


async def _reject(ws: WebSocket, code: str, message: str) -> None:
    try:
        await ws.send_json(session_mod.error_msg(code, message))
        await ws.close()
    except Exception:
        pass


@app.websocket("/ws/session")
async def ws_session(ws: WebSocket, patient_id: str = "", mode: str = "voice") -> None:
    await ws.accept()
    if mode not in ("voice", "text"):
        return await _reject(ws, "bad_message", "mode must be voice or text")
    try:
        case = load_case(patient_id)
    except InvalidPatientId:
        return await _reject(ws, "bad_message", "invalid patient_id")
    except CaseNotFound:
        return await _reject(ws, "not_found", "unknown patient_id")
    except ValueError:
        return await _reject(ws, "not_found", "patient case could not be loaded")
    if not session_mod.try_acquire():
        return await _reject(ws, "busy", "another session is already active")
    try:
        relay = session_mod.SessionRelay(ws, case, mode, settings_provider(), connect=upstream_connect)
        await relay.run()
    finally:
        session_mod.release()
