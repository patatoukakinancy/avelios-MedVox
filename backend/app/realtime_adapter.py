"""The ONLY place that knows OpenAI Realtime event names and payload shapes.

GA Realtime API (not beta), checked 2026-11-28 against:
  https://developers.openai.com/api/docs/guides/realtime-websocket
  https://developers.openai.com/api/docs/guides/realtime-conversations
  https://developers.openai.com/api/reference/resources/realtime/client-events
  https://developers.openai.com/api/reference/resources/realtime/server-events
  https://developers.openai.com/api/docs/models/gpt-realtime-2.1
GA renames vs beta: response.audio.* -> response.output_audio.*, response.audio_transcript.* ->
response.output_audio_transcript.*, response.text.* -> response.output_text.*, modalities -> output_modalities.
No "OpenAI-Beta" header in GA.

Three parts: session.update builder, client->upstream encoders, upstream->protocol translator.
The translator only ever emits CONTRACT.md messages; everything else is dropped.
"""
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .config import Settings
from .models import PatientCase
from .prompt import render_prompt

REALTIME_BASE_URL = "wss://api.openai.com/v1/realtime"
PCM_FORMAT = {"type": "audio/pcm", "rate": 24000}  # CONTRACT: PCM16, 24 kHz, mono
AUDIO_BYTES_PER_MS = 48  # 24000 samples/s * 2 bytes / 1000

# Internal signal kinds (not upstream names) consumed by session.py.
SESSION_UPDATED = "session_updated"
SPEECH_STARTED = "speech_started"
SPEECH_STOPPED = "speech_stopped"
COMMITTED = "committed"
RESPONSE_CREATED = "response_created"
AUDIO_DELTA = "audio_delta"
TEXT_DELTA = "text_delta"
RESPONSE_PART_DONE = "response_part_done"
RESPONSE_DONE = "response_done"
ERROR = "error"

_BENIGN_ERROR_CODES = {"response_cancel_not_active"}
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{4,}|Bearer\s+\S+|[A-Za-z0-9_\-]{32,})")
MAX_ERROR_MESSAGE = 120


@dataclass
class Signal:
    kind: str
    item_id: str | None = None
    response_id: str | None = None
    n_bytes: int = 0
    status: str | None = None
    usage: dict | None = None
    code: str | None = None
    message: str | None = None


@dataclass
class Translated:
    messages: list[dict] = field(default_factory=list)
    signal: Signal | None = None


# ---------- connection ----------

def realtime_url(model: str) -> str:
    return f"{REALTIME_BASE_URL}?model={quote(model, safe='')}"


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


# ---------- session.update ----------

def build_session_update(
    case: PatientCase, settings: Settings, mode: str, include_reasoning: bool = True
) -> dict:
    """mode="voice": audio out + server VAD + input transcription. mode="text": text out, no VAD.

    The patient never speaks first: this config never triggers a response by itself.
    """
    if mode not in ("voice", "text"):
        raise ValueError("mode must be voice or text")
    if mode == "voice":
        audio_in: dict[str, Any] = {
            "format": PCM_FORMAT,
            "turn_detection": {
                "type": "server_vad",
                "threshold": settings.vad_threshold,
                "prefix_padding_ms": settings.vad_prefix_padding_ms,
                "silence_duration_ms": settings.vad_silence_ms,
                "create_response": True,
                "interrupt_response": True,
            },
        }
        if settings.transcribe_model:
            audio_in["transcription"] = {"model": settings.transcribe_model}
    else:
        audio_in = {"format": PCM_FORMAT, "turn_detection": None}
    session: dict[str, Any] = {
        "type": "realtime",
        "output_modalities": ["audio"] if mode == "voice" else ["text"],
        "instructions": render_prompt(case),
        "audio": {
            "input": audio_in,
            "output": {"format": PCM_FORMAT, "voice": case.osce_behavior.voice.voice_id},
        },
        "max_output_tokens": settings.max_output_tokens,
    }
    if include_reasoning and settings.reasoning_effort:
        session["reasoning"] = {"effort": settings.reasoning_effort}
    return {"type": "session.update", "session": session}


# ---------- client -> upstream encoders ----------

def encode_audio_append(audio_b64: str) -> dict:
    return {"type": "input_audio_buffer.append", "audio": audio_b64}


def encode_user_text(text: str) -> dict:
    return {
        "type": "conversation.item.create",
        "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
    }


def encode_response_create() -> dict:
    return {"type": "response.create"}


def encode_response_cancel(response_id: str | None = None) -> dict:
    ev: dict[str, Any] = {"type": "response.cancel"}
    if response_id:
        ev["response_id"] = response_id
    return ev


def encode_truncate(item_id: str, audio_end_ms: int) -> dict:
    return {"type": "conversation.item.truncate", "item_id": item_id, "content_index": 0, "audio_end_ms": audio_end_ms}


# ---------- upstream -> protocol ----------

def sanitize_error_message(msg: Any) -> str:
    text = " ".join(str(msg or "upstream error").split())
    return _SECRET_RE.sub("[redacted]", text)[:MAX_ERROR_MESSAGE]


def is_benign_error(sig: Signal) -> bool:
    return sig.code in _BENIGN_ERROR_CODES


def _b64_len(s: str) -> int:
    return max(0, len(s) * 3 // 4 - s[-2:].count("=")) if s else 0


def _transcript(kind: str, role: str, item_id: Any, text: Any) -> dict:
    return {"type": kind, "role": role, "item_id": str(item_id or ""), "text": str(text or "")}


def translate(event: dict) -> Translated:
    t = event.get("type") if isinstance(event, dict) else None
    if t == "session.updated":
        return Translated(signal=Signal(SESSION_UPDATED))
    if t == "input_audio_buffer.speech_started":
        return Translated([{"type": "speech.started"}], Signal(SPEECH_STARTED, item_id=event.get("item_id")))
    if t == "input_audio_buffer.speech_stopped":
        return Translated(signal=Signal(SPEECH_STOPPED, item_id=event.get("item_id")))
    if t == "input_audio_buffer.committed":
        return Translated(signal=Signal(COMMITTED, item_id=event.get("item_id")))
    if t == "conversation.item.input_audio_transcription.delta":
        return Translated([_transcript("transcript.delta", "user", event.get("item_id"), event.get("delta"))])
    if t == "conversation.item.input_audio_transcription.completed":
        return Translated([_transcript("transcript.final", "user", event.get("item_id"), event.get("transcript"))])
    if t == "conversation.item.added":
        item = event.get("item") or {}
        if item.get("type") == "message" and item.get("role") == "user":
            texts = [c.get("text", "") for c in item.get("content") or [] if c.get("type") == "input_text"]
            if texts:
                return Translated([_transcript("transcript.final", "user", item.get("id"), " ".join(texts))])
        return Translated()
    if t == "response.created":
        return Translated(signal=Signal(RESPONSE_CREATED, response_id=(event.get("response") or {}).get("id")))
    if t == "response.output_audio.delta":
        delta = event.get("delta") or ""
        return Translated(
            [{"type": "audio.delta", "audio": delta}],
            Signal(AUDIO_DELTA, item_id=event.get("item_id"), response_id=event.get("response_id"), n_bytes=_b64_len(delta)),
        )
    if t in ("response.output_audio_transcript.delta", "response.output_text.delta"):
        return Translated(
            [_transcript("transcript.delta", "patient", event.get("item_id"), event.get("delta"))],
            Signal(TEXT_DELTA, item_id=event.get("item_id"), response_id=event.get("response_id")),
        )
    if t in ("response.output_audio_transcript.done", "response.output_text.done"):
        text = event.get("transcript") if t == "response.output_audio_transcript.done" else event.get("text")
        return Translated(
            [_transcript("transcript.final", "patient", event.get("item_id"), text)],
            Signal(RESPONSE_PART_DONE, item_id=event.get("item_id"), response_id=event.get("response_id")),
        )
    if t == "response.done":
        resp = event.get("response") or {}
        return Translated(signal=Signal(RESPONSE_DONE, response_id=resp.get("id"), status=resp.get("status"), usage=resp.get("usage")))
    if t == "error":
        err = event.get("error") or {}
        return Translated(signal=Signal(ERROR, code=str(err.get("code") or err.get("type") or "error"), message=sanitize_error_message(err.get("message"))))
    return Translated()


def accumulate_usage(total: dict, usage: Any) -> dict:
    """Recursive numeric sum of response.usage objects."""
    if not isinstance(usage, dict):
        return total
    for k, v in usage.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            total[k] = total.get(k, 0) + v
        elif isinstance(v, dict):
            sub = total.get(k)
            total[k] = accumulate_usage(sub if isinstance(sub, dict) else {}, v)
    return total
