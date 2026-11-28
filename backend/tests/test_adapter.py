"""Adapter: session.update builder, encoders, upstream->protocol translation. No network."""
import base64
import json

import pytest

from app import realtime_adapter as rt
from app.cases import load_case
from app.config import Settings

S = Settings(openai_api_key="sk-test-not-real", realtime_model="m", transcribe_model="tm",
             max_output_tokens=150, vad_threshold=0.6, vad_silence_ms=450, vad_prefix_padding_ms=250)

CONTRACT_TYPES = {"session.ready", "speech.started", "audio.delta", "transcript.delta", "transcript.final",
                  "latency", "error", "session.ended"}


@pytest.mark.parametrize("pid,voice", [("case_01", "ash"), ("case_02", "sage")])
def test_session_update_voice(pid, voice):
    case = load_case(pid)
    ev = rt.build_session_update(case, S, "voice")
    assert ev["type"] == "session.update"
    s = ev["session"]
    assert s["type"] == "realtime"
    assert s["output_modalities"] == ["audio"]
    assert s["audio"]["output"]["voice"] == voice
    assert s["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert s["audio"]["input"]["transcription"] == {"model": "tm"}
    td = s["audio"]["input"]["turn_detection"]
    assert td == {"type": "server_vad", "threshold": 0.6, "prefix_padding_ms": 250,
                  "silence_duration_ms": 450, "create_response": True, "interrupt_response": True}
    assert s["max_output_tokens"] == 150
    assert s["reasoning"] == {"effort": "minimal"}
    assert "model" not in s
    payload = json.dumps(ev)
    for fact in case.clinical_background.facts:
        assert fact.truth not in payload


def test_session_update_text_mode_same_instructions():
    case = load_case("case_01")
    v = rt.build_session_update(case, S, "voice")["session"]
    t = rt.build_session_update(case, S, "text")["session"]
    assert t["output_modalities"] == ["text"]
    assert t["audio"]["input"]["turn_detection"] is None
    assert "transcription" not in t["audio"]["input"]
    assert t["instructions"] == v["instructions"]


def test_session_update_reasoning_optional():
    case = load_case("case_01")
    assert "reasoning" not in rt.build_session_update(case, S, "voice", include_reasoning=False)["session"]
    no_effort = Settings(realtime_model="m", reasoning_effort=None)
    assert "reasoning" not in rt.build_session_update(case, no_effort, "voice")["session"]


def test_session_update_without_transcribe_model():
    s = rt.build_session_update(load_case("case_01"), Settings(realtime_model="m"), "voice")["session"]
    assert "transcription" not in s["audio"]["input"]


def test_encoders():
    assert rt.encode_audio_append("AAA=") == {"type": "input_audio_buffer.append", "audio": "AAA="}
    assert rt.encode_user_text("hi") == {"type": "conversation.item.create", "item": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}}
    assert rt.encode_response_create() == {"type": "response.create"}
    assert rt.encode_response_cancel("r1") == {"type": "response.cancel", "response_id": "r1"}
    assert rt.encode_response_cancel() == {"type": "response.cancel"}
    assert rt.encode_truncate("i1", 900) == {"type": "conversation.item.truncate", "item_id": "i1",
                                             "content_index": 0, "audio_end_ms": 900}
    assert rt.realtime_url("gpt-x") == "wss://api.openai.com/v1/realtime?model=gpt-x"
    assert rt.auth_headers("k") == {"Authorization": "Bearer k"}


def test_translate_audio_delta():
    b64 = base64.b64encode(b"\x00" * 4800).decode()
    tr = rt.translate({"type": "response.output_audio.delta", "response_id": "r1", "item_id": "i1",
                       "output_index": 0, "content_index": 0, "delta": b64})
    assert tr.messages == [{"type": "audio.delta", "audio": b64}]
    assert tr.signal.kind == rt.AUDIO_DELTA and tr.signal.n_bytes == 4800
    assert tr.signal.item_id == "i1" and tr.signal.response_id == "r1"


@pytest.mark.parametrize("event,expected", [
    ({"type": "response.output_audio_transcript.delta", "item_id": "i1", "response_id": "r", "delta": "Hel"},
     {"type": "transcript.delta", "role": "patient", "item_id": "i1", "text": "Hel"}),
    ({"type": "response.output_audio_transcript.done", "item_id": "i1", "response_id": "r", "transcript": "Hello."},
     {"type": "transcript.final", "role": "patient", "item_id": "i1", "text": "Hello."}),
    ({"type": "response.output_text.delta", "item_id": "i2", "response_id": "r", "delta": "Hi"},
     {"type": "transcript.delta", "role": "patient", "item_id": "i2", "text": "Hi"}),
    ({"type": "response.output_text.done", "item_id": "i2", "response_id": "r", "text": "Hi there."},
     {"type": "transcript.final", "role": "patient", "item_id": "i2", "text": "Hi there."}),
    ({"type": "conversation.item.input_audio_transcription.delta", "item_id": "u1", "content_index": 0, "delta": "my"},
     {"type": "transcript.delta", "role": "user", "item_id": "u1", "text": "my"}),
    ({"type": "conversation.item.input_audio_transcription.completed", "item_id": "u1", "content_index": 0,
      "transcript": "my chest hurts"},
     {"type": "transcript.final", "role": "user", "item_id": "u1", "text": "my chest hurts"}),
    ({"type": "conversation.item.added", "item": {"id": "u2", "type": "message", "role": "user",
                                                  "content": [{"type": "input_text", "text": "Hello"}]}},
     {"type": "transcript.final", "role": "user", "item_id": "u2", "text": "Hello"}),
    ({"type": "input_audio_buffer.speech_started", "audio_start_ms": 10, "item_id": "u3"},
     {"type": "speech.started"}),
])
def test_translate_to_contract(event, expected):
    assert rt.translate(event).messages == [expected]


@pytest.mark.parametrize("event", [
    {"type": "session.created", "session": {"instructions": "SECRET PROMPT"}},
    {"type": "session.updated", "session": {"instructions": "SECRET PROMPT"}},
    {"type": "response.created", "response": {"id": "r1"}},
    {"type": "response.done", "response": {"id": "r1", "status": "completed", "usage": {"total_tokens": 3}}},
    {"type": "input_audio_buffer.speech_stopped", "item_id": "u"},
    {"type": "input_audio_buffer.committed", "item_id": "u"},
    {"type": "conversation.item.added", "item": {"id": "a", "type": "message", "role": "assistant", "content": []}},
    {"type": "conversation.item.added", "item": {"id": "u", "type": "message", "role": "user",
                                                 "content": [{"type": "input_audio"}]}},
    {"type": "rate_limits.updated", "rate_limits": []},
    {"type": "something.new"},
    {"no_type": True},
])
def test_non_contract_events_emit_nothing(event):
    assert rt.translate(event).messages == []


def test_signals():
    assert rt.translate({"type": "session.updated"}).signal.kind == rt.SESSION_UPDATED
    assert rt.translate({"type": "input_audio_buffer.speech_stopped"}).signal.kind == rt.SPEECH_STOPPED
    assert rt.translate({"type": "input_audio_buffer.committed"}).signal.kind == rt.COMMITTED
    sig = rt.translate({"type": "response.created", "response": {"id": "r9"}}).signal
    assert (sig.kind, sig.response_id) == (rt.RESPONSE_CREATED, "r9")
    sig = rt.translate({"type": "response.done", "response": {"id": "r9", "status": "cancelled",
                                                              "usage": {"total_tokens": 5}}}).signal
    assert (sig.kind, sig.status, sig.usage) == (rt.RESPONSE_DONE, "cancelled", {"total_tokens": 5})


def test_error_is_sanitized():
    secret = "sk-proj-" + "A" * 40
    tr = rt.translate({"type": "error", "event_id": "e", "error": {
        "type": "invalid_request_error", "code": "bad_key",
        "message": f"Incorrect API key provided: {secret}. Bearer {secret}\n" + "x" * 500}})
    assert tr.messages == []
    assert tr.signal.kind == rt.ERROR and tr.signal.code == "bad_key"
    assert secret not in tr.signal.message and "AAAAAAAA" not in tr.signal.message
    assert len(tr.signal.message) <= rt.MAX_ERROR_MESSAGE
    assert "\n" not in tr.signal.message


def test_benign_cancel_error():
    sig = rt.translate({"type": "error", "error": {"code": "response_cancel_not_active", "message": "x"}}).signal
    assert rt.is_benign_error(sig)


def test_accumulate_usage():
    total: dict = {}
    u1 = {"total_tokens": 10, "input_tokens": 7, "output_tokens": 3,
          "input_token_details": {"text_tokens": 7, "cached_tokens": 0, "cached_tokens_details": {"text_tokens": 0}},
          "output_token_details": {"audio_tokens": 2, "text_tokens": 1}}
    u2 = {"total_tokens": 5, "input_tokens": 4, "output_tokens": 1,
          "input_token_details": {"text_tokens": 4, "cached_tokens": 4, "cached_tokens_details": {"text_tokens": 4}},
          "output_token_details": {"audio_tokens": 0, "text_tokens": 1}}
    rt.accumulate_usage(total, u1)
    rt.accumulate_usage(total, u2)
    rt.accumulate_usage(total, None)
    assert total["total_tokens"] == 15 and total["input_tokens"] == 11
    assert total["input_token_details"]["cached_tokens"] == 4
    assert total["input_token_details"]["cached_tokens_details"]["text_tokens"] == 4
    assert total["output_token_details"] == {"audio_tokens": 2, "text_tokens": 2}
