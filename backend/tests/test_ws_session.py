"""WS /ws/session end-to-end against a FAKE upstream (no network)."""
import asyncio
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app import session as session_mod
from app.config import Settings

CLOSE = object()
AUDIO_100MS = base64.b64encode(b"\x00" * 4800).decode()


class FakeUpstream:
    def __init__(self, script):
        self.script = script
        self.sent: list[dict] = []
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        ev = json.loads(data)
        self.sent.append(ev)
        for reply in self.script(ev):
            await self.inbox.put(reply)

    async def recv(self):
        item = await self.inbox.get()
        if item is CLOSE:
            raise ConnectionError("upstream gone")
        return json.dumps(item)

    async def close(self):
        self.closed = True


def text_reply(ev, n=[0]):
    """Accept session.update; answer response.create with a short text reply + usage."""
    t = ev["type"]
    if t == "session.update":
        return [{"type": "session.created"}, {"type": "session.updated", "session": ev["session"]}]
    if t == "conversation.item.create":
        return [{"type": "conversation.item.added", "item": {"id": "u_item", **ev["item"]}}]
    if t == "response.create":
        n[0] += 1
        rid, iid = f"resp_{n[0]}", f"item_{n[0]}"
        return [
            {"type": "response.created", "response": {"id": rid}},
            {"type": "response.output_text.delta", "response_id": rid, "item_id": iid, "delta": "It's my "},
            {"type": "response.output_text.delta", "response_id": rid, "item_id": iid, "delta": "chest."},
            {"type": "response.output_text.done", "response_id": rid, "item_id": iid, "text": "It's my chest."},
            {"type": "response.done", "response": {"id": rid, "status": "completed",
                                                   "usage": {"total_tokens": 10, "output_tokens": 4}}},
        ]
    return []


@pytest.fixture
def harness(tmp_path, monkeypatch):
    state = {"script": text_reply, "ups": [], "settings": Settings(
        openai_api_key="sk-test-not-real", realtime_model="fake-model", transcribe_model="fake-transcribe",
        max_session_seconds=30, idle_timeout_seconds=30, latency_log_path=tmp_path / "latency.jsonl")}

    async def connect(url, headers):
        up = FakeUpstream(state["script"])
        state["ups"].append(up)
        return up

    monkeypatch.setattr(main, "upstream_connect", connect)
    monkeypatch.setattr(main, "settings_provider", lambda: state["settings"])
    session_mod.release()
    yield state
    session_mod.release()


def recv_until(ws, type_, limit=50):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if m["type"] == type_:
            return seen
    raise AssertionError(f"{type_} not received: {seen}")


@pytest.mark.parametrize("query,code", [
    ("patient_id=../x&mode=text", "bad_message"),
    ("patient_id=case_99&mode=text", "not_found"),
    ("patient_id=case_01&mode=loud", "bad_message"),
])
def test_rejected_before_upstream(harness, query, code):
    with TestClient(main.app).websocket_connect(f"/ws/session?{query}") as ws:
        assert ws.receive_json()["code"] == code
    assert harness["ups"] == []


def test_busy(harness):
    assert session_mod.try_acquire()
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=text") as ws:
        assert ws.receive_json() == {"type": "error", "code": "busy", "message": "another session is already active"}
    assert harness["ups"] == []


def test_text_session_full_flow(harness):
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=text") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "session.ready" and ready["mode"] == "text"
        assert set(ready["patient_public"]) == {"display_name", "age", "sex", "setting", "presenting_complaint",
                                                "difficulty", "estimated_minutes"}
        up = harness["ups"][0]
        assert [e["type"] for e in up.sent] == ["session.update"]  # patient never speaks first
        for i in range(3):
            ws.send_json({"type": "text.send", "text": f"question {i}"})
            msgs = recv_until(ws, "latency")
            types = [m["type"] for m in msgs]
            assert types[0] == "transcript.final" and msgs[0]["role"] == "user"
            assert "transcript.delta" in types and "audio.delta" not in types
            lat = msgs[-1]
            assert lat["turn"] == i + 1 and lat["ttfa_ms"] is None and isinstance(lat["ttft_ms"], int)
            assert lat["vad_silence_ms"] is None
            assert all(m["type"] in {"transcript.delta", "transcript.final", "latency"} for m in msgs)
        ws.send_json({"type": "session.end"})
        ended = recv_until(ws, "session.ended")[-1]
    assert ended == {"type": "session.ended", "reason": "client", "turns": 3,
                     "usage": {"total_tokens": 30, "output_tokens": 12}}
    lines = harness["settings"].latency_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert not session_mod.is_busy() and up.closed


def test_bad_messages_keep_session_alive(harness):
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_02&mode=text") as ws:
        ws.receive_json()
        for bad in ["{not json", json.dumps({"type": "nope"}), json.dumps([1]),
                    json.dumps({"type": "audio.append", "audio": "AAAA"}),  # text mode
                    json.dumps({"type": "interrupt", "played_ms": -1})]:
            ws.send_text(bad)
            assert ws.receive_json()["code"] == "bad_message"
        ws.send_json({"type": "text.send", "text": "hello"})
        assert recv_until(ws, "latency")[-1]["turn"] == 1


def test_audio_over_1mb_rejected(harness):
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        assert ws.receive_json()["mode"] == "voice"
        ws.send_json({"type": "audio.append", "audio": "A" * (1024 * 1024 + 4)})
        assert ws.receive_json()["code"] == "bad_message"
        ws.send_json({"type": "audio.append", "audio": AUDIO_100MS})
        ws.send_json({"type": "session.end"})
        recv_until(ws, "session.ended")
    sent = [e["type"] for e in harness["ups"][0].sent]
    assert sent == ["session.update", "input_audio_buffer.append"]


def test_fallback_drops_reasoning(harness):
    def script(ev):
        if ev["type"] == "session.update" and "reasoning" in ev["session"]:
            return [{"type": "error", "error": {"code": "unknown_parameter", "message": "reasoning"}}]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        assert ws.receive_json()["mode"] == "voice"
    ups = harness["ups"]
    assert len(ups) == 2
    assert "reasoning" in ups[0].sent[0]["session"] and "reasoning" not in ups[1].sent[0]["session"]
    assert ups[1].sent[0]["session"]["output_modalities"] == ["audio"]


def test_fallback_to_text(harness):
    def script(ev):
        if ev["type"] == "session.update" and ev["session"]["output_modalities"] == ["audio"]:
            return [{"type": "error", "error": {"code": "invalid_value", "message": "no audio"}}]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        assert ws.receive_json()["mode"] == "text"
    assert len(harness["ups"]) == 3


def test_fallback_all_fail(harness):
    harness["script"] = lambda ev: [{"type": "error", "error": {"code": "x", "message": "nope"}}]
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        assert ws.receive_json()["code"] == "upstream_closed"
        assert ws.receive_json()["reason"] == "error"
    assert len(harness["ups"]) == 3 and all(u.closed for u in harness["ups"])
    assert not session_mod.is_busy()


def test_upstream_drop_mid_session(harness):
    def script(ev):
        if ev["type"] == "response.create":
            return [CLOSE]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=text") as ws:
        ws.receive_json()
        ws.send_json({"type": "text.send", "text": "hi"})
        msgs = recv_until(ws, "session.ended")
    assert {"type": "error", "code": "upstream_closed", "message": "connection to the voice service was lost"} in msgs
    assert msgs[-1]["reason"] == "error"
    assert not session_mod.is_busy()


def test_upstream_error_forwarded_short(harness):
    def script(ev):
        if ev["type"] == "response.create":
            return [{"type": "error", "error": {"code": "server_error", "message": "boom sk-" + "B" * 40}},
                    {"type": "error", "error": {"code": "response_cancel_not_active", "message": "none"}}]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=text") as ws:
        ws.receive_json()
        ws.send_json({"type": "text.send", "text": "hi"})
        err = recv_until(ws, "error")[-1]
        ws.send_json({"type": "session.end"})
        rest = recv_until(ws, "session.ended")
    assert err["code"] == "upstream_error" and "BBBB" not in err["message"]
    assert all(m["type"] != "error" for m in rest)  # benign cancel error dropped


def test_interrupt_truncates_to_heard_audio(harness):
    def script(ev):
        if ev["type"] == "response.create":
            return [{"type": "response.created", "response": {"id": "r1"}},
                    {"type": "response.output_audio.delta", "response_id": "r1", "item_id": "a1", "delta": AUDIO_100MS}]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        ws.receive_json()
        ws.send_json({"type": "text.send", "text": "hi"})
        recv_until(ws, "audio.delta")
        ws.send_json({"type": "interrupt", "played_ms": 5000})
        ws.send_json({"type": "session.end"})
        recv_until(ws, "session.ended")
    sent = harness["ups"][0].sent
    assert {"type": "response.cancel", "response_id": "r1"} in sent
    assert {"type": "conversation.item.truncate", "item_id": "a1", "content_index": 0, "audio_end_ms": 100} in sent


def test_speech_started_forwarded_and_voice_latency(harness):
    def script(ev):
        if ev["type"] == "input_audio_buffer.append":
            return [{"type": "input_audio_buffer.speech_started", "item_id": "u1", "audio_start_ms": 0},
                    {"type": "input_audio_buffer.speech_stopped", "item_id": "u1", "audio_end_ms": 900},
                    {"type": "input_audio_buffer.committed", "item_id": "u1"},
                    {"type": "response.created", "response": {"id": "r1"}},
                    {"type": "response.output_audio.delta", "response_id": "r1", "item_id": "a1", "delta": AUDIO_100MS},
                    {"type": "response.done", "response": {"id": "r1", "status": "completed", "usage": {"total_tokens": 1}}}]
        return text_reply(ev)
    harness["script"] = script
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio.append", "audio": AUDIO_100MS})
        msgs = recv_until(ws, "latency")
    assert msgs[0] == {"type": "speech.started"}
    assert msgs[1] == {"type": "audio.delta", "audio": AUDIO_100MS}
    lat = msgs[-1]
    assert isinstance(lat["ttfa_ms"], int) and lat["vad_silence_ms"] == harness["settings"].vad_silence_ms


def test_audio_append_does_not_refresh_idle(harness):
    s = harness["settings"]
    harness["settings"] = Settings(openai_api_key=s.openai_api_key, realtime_model=s.realtime_model,
                                   idle_timeout_seconds=0.4, max_session_seconds=30,
                                   latency_log_path=s.latency_log_path)
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=voice") as ws:
        ws.receive_json()
        start = time.monotonic()
        for _ in range(4):
            ws.send_json({"type": "audio.append", "audio": AUDIO_100MS})
            time.sleep(0.05)
        ended = recv_until(ws, "session.ended")[-1]
    assert ended["reason"] == "idle"
    assert time.monotonic() - start < 3


def test_session_timeout(harness):
    s = harness["settings"]
    harness["settings"] = Settings(openai_api_key=s.openai_api_key, realtime_model=s.realtime_model,
                                   idle_timeout_seconds=30, max_session_seconds=0.3,
                                   latency_log_path=s.latency_log_path)
    with TestClient(main.app).websocket_connect("/ws/session?patient_id=case_01&mode=text") as ws:
        ws.receive_json()
        assert recv_until(ws, "session.ended")[-1]["reason"] == "timeout"
    assert not session_mod.is_busy()
