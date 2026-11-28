import json

from app.latency import LatencyTracker, append_jsonl


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, ms):
        self.t += ms / 1000


def test_voice_turn_ttfa_and_ttft_first_delta_only():
    c = FakeClock()
    lt = LatencyTracker(clock=c, vad_silence_ms=500)
    lt.start_turn("voice")
    c.advance(120)
    lt.mark_text()
    c.advance(200)
    lt.mark_audio()
    c.advance(300)
    lt.mark_audio()
    lt.mark_text()
    assert lt.finish() == {"turn": 1, "ttfa_ms": 320, "ttft_ms": 120, "vad_silence_ms": 500}
    assert lt.finish() is None


def test_text_turn_has_no_vad_silence():
    c = FakeClock()
    lt = LatencyTracker(clock=c, vad_silence_ms=500)
    lt.start_turn("text")
    c.advance(250)
    lt.mark_text()
    assert lt.finish() == {"turn": 1, "ttfa_ms": None, "ttft_ms": 250, "vad_silence_ms": None}


def test_committed_does_not_restart_active_turn():
    c = FakeClock()
    lt = LatencyTracker(clock=c, vad_silence_ms=400)
    lt.start_turn("voice")              # speech_stopped
    c.advance(50)
    lt.start_turn("voice", only_if_idle=True)  # committed: ignored
    c.advance(100)
    lt.mark_audio()
    assert lt.finish()["ttfa_ms"] == 150


def test_committed_fallback_starts_turn():
    c = FakeClock()
    lt = LatencyTracker(clock=c)
    lt.start_turn("voice", only_if_idle=True)
    c.advance(80)
    lt.mark_audio()
    assert lt.finish()["ttfa_ms"] == 80


def test_turn_counter_and_restart_keeps_number():
    c = FakeClock()
    lt = LatencyTracker(clock=c)
    for _ in range(3):
        lt.start_turn("text")
        lt.mark_text()
        lt.finish()
    assert lt.turns == 3
    lt.start_turn("voice")
    lt.start_turn("voice")  # unfinished turn replaced, not counted twice
    assert lt.turns == 4
    assert lt.finish()["turn"] == 4


def test_marks_without_turn_ignored():
    lt = LatencyTracker(clock=FakeClock())
    lt.mark_audio()
    lt.mark_text()
    assert lt.finish() is None and lt.turns == 0


def test_append_jsonl(tmp_path):
    path = tmp_path / "logs" / "latency.jsonl"
    append_jsonl(path, "s1", {"turn": 1, "ttfa_ms": None, "ttft_ms": 210, "vad_silence_ms": None})
    append_jsonl(path, "s1", {"turn": 2, "ttfa_ms": 400, "ttft_ms": 300, "vad_silence_ms": 500})
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert set(lines[0]) == {"session_id", "turn", "ttfa_ms", "ttft_ms", "vad_silence_ms", "ts"}
    assert lines[1]["turn"] == 2 and lines[1]["vad_silence_ms"] == 500 and lines[1]["session_id"] == "s1"
