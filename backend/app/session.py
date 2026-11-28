"""SessionRelay: one client WebSocket <-> one OpenAI Realtime upstream WebSocket.

Upstream event names/shapes live only in realtime_adapter.py. Only CONTRACT.md messages reach the client.
"""
import asyncio
import json
import logging
import uuid
from typing import Awaitable, Callable, Protocol

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from . import realtime_adapter as rt
from .config import Settings
from .latency import LatencyTracker, append_jsonl
from .models import PatientCase

log = logging.getLogger("medvox.session")

MAX_AUDIO_B64_CHARS = 1024 * 1024  # 1 MB per audio.append payload
MAX_TEXT_CHARS = 2000
SETUP_TIMEOUT_SECONDS = 10.0


class Upstream(Protocol):
    async def send(self, data: str) -> None: ...
    async def recv(self) -> str: ...
    async def close(self) -> None: ...


Connect = Callable[[str, dict], Awaitable[Upstream]]


async def default_connect(url: str, headers: dict) -> Upstream:
    from websockets.asyncio.client import connect

    return await connect(url, additional_headers=headers, open_timeout=10, max_size=8 * 1024 * 1024)


# ---------- one active session globally ----------
_active = False


def try_acquire() -> bool:
    global _active
    if _active:
        return False
    _active = True
    return True


def release() -> None:
    global _active
    _active = False


def is_busy() -> bool:
    return _active


def error_msg(code: str, message: str) -> dict:
    return {"type": "error", "code": code, "message": message}


class SessionRelay:
    def __init__(self, client: WebSocket, case: PatientCase, mode: str, settings: Settings, connect: Connect = default_connect):
        self.client = client
        self.case = case
        self.requested_mode = mode
        self.mode = mode
        self.settings = settings
        self.connect = connect
        self.session_id = uuid.uuid4().hex[:12]
        self.upstream: Upstream | None = None
        self.latency = LatencyTracker(vad_silence_ms=settings.vad_silence_ms)
        self.usage: dict = {}
        self._send_lock = asyncio.Lock()
        self._client_gone = False
        self._ended = False
        self._end_reason: str | None = None
        self._upstream_failed = False
        self._active_response: str | None = None
        self._cancelled: set[str] = set()
        self._audio_item: str | None = None
        self._audio_item_bytes = 0
        self._loop = asyncio.get_running_loop()
        self._started = self._loop.time()
        self._last_input = self._started

    # ---------- helpers ----------
    def _now(self) -> float:
        return self._loop.time()

    async def _send(self, msg: dict) -> None:
        if self._client_gone:
            return
        try:
            async with self._send_lock:
                await self.client.send_text(json.dumps(msg))
        except Exception:
            self._client_gone = True

    async def _up_send(self, event: dict) -> bool:
        if self.upstream is None:
            return False
        try:
            await self.upstream.send(json.dumps(event))
            return True
        except Exception as exc:
            log.warning("upstream send failed: %s", type(exc).__name__)
            await self._fail_upstream()
            return False

    async def _fail_upstream(self) -> None:
        if self._upstream_failed:
            return
        self._upstream_failed = True
        if self._end_reason is None:
            self._end_reason = "error"
            await self._send(error_msg("upstream_closed", "connection to the voice service was lost"))

    def _finish(self, reason: str) -> None:
        if self._end_reason is None:
            self._end_reason = reason

    async def _end(self) -> None:
        if self._ended:
            return
        self._ended = True
        reason = self._end_reason or "error"
        log.info("session %s ended reason=%s turns=%d secs=%.1f", self.session_id, reason, self.latency.turns, self._now() - self._started)
        await self._send({"type": "session.ended", "reason": reason, "turns": self.latency.turns, "usage": self.usage})

    async def _close_upstream(self, up: Upstream | None) -> None:
        if up is None:
            return
        try:
            await asyncio.wait_for(up.close(), 5)
        except BaseException:  # never let close errors escape cleanup
            pass

    # ---------- upstream setup with fallback chain ----------
    def _attempts(self) -> list[tuple[str, bool]]:
        has_reasoning = bool(self.settings.reasoning_effort)
        chain: list[tuple[str, bool]] = []
        if self.requested_mode == "voice":
            chain.append(("voice", True))
            if has_reasoning:
                chain.append(("voice", False))
            chain.append(("text", False))
        else:
            chain.append(("text", True))
            if has_reasoning:
                chain.append(("text", False))
        return chain

    async def _try_open(self, mode: str, reasoning: bool) -> Upstream | None:
        try:
            up = await self.connect(rt.realtime_url(self.settings.realtime_model), rt.auth_headers(self.settings.openai_api_key))
        except Exception as exc:
            log.warning("upstream connect failed (%s, reasoning=%s): %s", mode, reasoning, type(exc).__name__)
            return None
        try:
            await up.send(json.dumps(rt.build_session_update(self.case, self.settings, mode, include_reasoning=reasoning)))
            ok = await asyncio.wait_for(self._await_session_updated(up), SETUP_TIMEOUT_SECONDS)
        except Exception as exc:
            log.warning("upstream setup failed (%s, reasoning=%s): %s", mode, reasoning, type(exc).__name__)
            ok = False
        if not ok:
            await self._close_upstream(up)
            return None
        return up

    async def _await_session_updated(self, up: Upstream) -> bool:
        while True:
            try:
                event = json.loads(await up.recv())
            except json.JSONDecodeError:
                continue
            sig = rt.translate(event).signal
            if sig and sig.kind == rt.SESSION_UPDATED:
                return True
            if sig and sig.kind == rt.ERROR:
                log.warning("session.update rejected: code=%s", sig.code)
                return False

    async def _open_upstream(self) -> bool:
        if not self.settings.upstream_configured:
            log.warning("upstream not configured (OPENAI_API_KEY / REALTIME_MODEL missing)")
            return False
        for mode, reasoning in self._attempts():
            up = await self._try_open(mode, reasoning)
            if up is not None:
                self.upstream = up
                self.mode = mode
                log.info("session %s upstream ready mode=%s reasoning=%s", self.session_id, mode, reasoning and bool(self.settings.reasoning_effort))
                return True
        return False

    # ---------- main ----------
    async def run(self) -> None:
        tasks: list[asyncio.Task] = []
        try:
            if not await self._open_upstream():
                self._end_reason = "error"
                await self._send(error_msg("upstream_closed", "voice service unavailable"))
                return
            await self._send({"type": "session.ready", "patient_public": self.case.public_card.model_dump(), "mode": self.mode})
            # The patient never speaks first: no response.create here.
            tasks = [
                asyncio.create_task(self._client_loop()),
                asyncio.create_task(self._upstream_loop()),
                asyncio.create_task(self._watchdog()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if not t.cancelled() and t.exception() is not None:
                    log.error("session task crashed: %s", type(t.exception()).__name__)
                    self._finish("error")
        finally:
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self._close_upstream(self.upstream)
            self.upstream = None
            await self._end()
            if not self._client_gone:
                try:
                    await self.client.close()
                except Exception:
                    pass

    # ---------- client -> upstream ----------
    async def _client_loop(self) -> None:
        while self._end_reason is None:
            try:
                message = await self.client.receive()
            except (WebSocketDisconnect, RuntimeError):
                self._client_gone = True
                self._finish("client")
                return
            if message.get("type") == "websocket.disconnect":
                self._client_gone = True
                self._finish("client")
                return
            raw = message.get("text")
            if raw is None:
                await self._send(error_msg("bad_message", "expected a JSON text frame"))
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await self._send(error_msg("bad_message", "malformed JSON"))
                continue
            if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
                await self._send(error_msg("bad_message", "missing message type"))
                continue
            await self._handle_client(msg)

    async def _handle_client(self, msg: dict) -> None:
        t = msg["type"]
        if t == "audio.append":
            # Deliberately does NOT refresh the idle clock: an open mic streams silence.
            if self.mode != "voice":
                await self._send(error_msg("bad_message", "audio is not accepted in text mode"))
                return
            audio = msg.get("audio")
            if not isinstance(audio, str) or not audio:
                await self._send(error_msg("bad_message", "audio must be a base64 string"))
                return
            if len(audio) > MAX_AUDIO_B64_CHARS:
                await self._send(error_msg("bad_message", "audio frame larger than 1 MB"))
                return
            await self._up_send(rt.encode_audio_append(audio))
        elif t == "text.send":
            text = msg.get("text")
            if not isinstance(text, str) or not text.strip():
                await self._send(error_msg("bad_message", "text must be a non-empty string"))
                return
            if len(text) > MAX_TEXT_CHARS:
                await self._send(error_msg("bad_message", "text too long"))
                return
            self._last_input = self._now()
            self.latency.start_turn("text")
            log.info("session %s text.send chars=%d", self.session_id, len(text))
            if await self._up_send(rt.encode_user_text(text.strip())):
                await self._up_send(rt.encode_response_create())
        elif t == "interrupt":
            played = msg.get("played_ms")
            if isinstance(played, bool) or not isinstance(played, (int, float)) or played < 0:
                await self._send(error_msg("bad_message", "played_ms must be a non-negative number"))
                return
            self._last_input = self._now()
            await self._interrupt(int(played))
        elif t == "session.end":
            self._finish("client")
        else:
            await self._send(error_msg("bad_message", "unknown message type"))

    async def _interrupt(self, played_ms: int) -> None:
        if self._active_response and self._active_response not in self._cancelled:
            self._cancelled.add(self._active_response)
            await self._up_send(rt.encode_response_cancel(self._active_response))
        if self._audio_item:
            heard = min(played_ms, self._audio_item_bytes // rt.AUDIO_BYTES_PER_MS)
            await self._up_send(rt.encode_truncate(self._audio_item, heard))
            log.info("session %s truncate audio_end_ms=%d", self.session_id, heard)

    # ---------- upstream -> client ----------
    async def _upstream_loop(self) -> None:
        assert self.upstream is not None
        while self._end_reason is None:
            try:
                raw = await self.upstream.recv()
            except Exception as exc:
                log.warning("upstream closed: %s", type(exc).__name__)
                await self._fail_upstream()
                return
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            await self._handle_upstream(event)

    async def _handle_upstream(self, event: dict) -> None:
        tr = rt.translate(event)
        sig = tr.signal
        if sig is not None:
            k = sig.kind
            if k in (rt.AUDIO_DELTA, rt.TEXT_DELTA) and sig.response_id in self._cancelled:
                return  # stale output of a cancelled (barged-in) response
            if k == rt.SPEECH_STARTED:
                self._last_input = self._now()
            elif k == rt.SPEECH_STOPPED:
                self.latency.start_turn("voice")
            elif k == rt.COMMITTED:
                self.latency.start_turn("voice", only_if_idle=True)
            elif k == rt.RESPONSE_CREATED:
                self._active_response = sig.response_id
            elif k == rt.AUDIO_DELTA:
                self.latency.mark_audio()
                if sig.item_id != self._audio_item:
                    self._audio_item = sig.item_id
                    self._audio_item_bytes = 0
                self._audio_item_bytes += sig.n_bytes
            elif k == rt.TEXT_DELTA:
                self.latency.mark_text()
            elif k == rt.RESPONSE_DONE:
                rt.accumulate_usage(self.usage, sig.usage)
                if self._active_response == sig.response_id:
                    self._active_response = None
                record = self.latency.finish()
                if record is not None:
                    await self._send({"type": "latency", **record})
                    log.info("session %s turn=%d ttfa_ms=%s ttft_ms=%s status=%s", self.session_id, record["turn"], record["ttfa_ms"], record["ttft_ms"], sig.status)
                    try:
                        append_jsonl(self.settings.latency_log_path, self.session_id, record)
                    except OSError as exc:
                        log.warning("latency log write failed: %s", type(exc).__name__)
            elif k == rt.ERROR:
                if rt.is_benign_error(sig):
                    return
                log.warning("upstream error code=%s", sig.code)
                await self._send(error_msg("upstream_error", sig.message or "upstream error"))
                return
        for m in tr.messages:
            await self._send(m)

    # ---------- caps ----------
    async def _watchdog(self) -> None:
        tick = max(0.05, min(0.5, self.settings.idle_timeout_seconds / 4, self.settings.max_session_seconds / 4))
        while self._end_reason is None:
            await asyncio.sleep(tick)
            now = self._now()
            if now - self._started >= self.settings.max_session_seconds:
                self._finish("timeout")
            elif now - self._last_input >= self.settings.idle_timeout_seconds:
                self._finish("idle")
