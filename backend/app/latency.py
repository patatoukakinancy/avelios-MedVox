"""Per-turn latency. Voice: t0 = speech stopped (fallback: buffer committed), t1 = first audio delta (ttfa).
Text/any: t1 = first text or audio-transcript delta (ttft). Clock is injectable for tests."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class LatencyTracker:
    def __init__(self, clock: Callable[[], float] = time.monotonic, vad_silence_ms: int | None = None):
        self._clock = clock
        self._vad_silence_ms = vad_silence_ms
        self.turns = 0
        self._active = False
        self._kind: str | None = None
        self._t0 = 0.0
        self._ttfa: int | None = None
        self._ttft: int | None = None

    @property
    def active(self) -> bool:
        return self._active

    def start_turn(self, kind: str, only_if_idle: bool = False) -> None:
        """kind: "voice" | "text". A restart while active keeps the turn number (unfinished turn replaced)."""
        if self._active and only_if_idle:
            return
        if not self._active:
            self.turns += 1
        self._active = True
        self._kind = kind
        self._t0 = self._clock()
        self._ttfa = None
        self._ttft = None

    def _elapsed_ms(self) -> int:
        return max(0, round((self._clock() - self._t0) * 1000))

    def mark_audio(self) -> None:
        if self._active and self._ttfa is None:
            self._ttfa = self._elapsed_ms()

    def mark_text(self) -> None:
        if self._active and self._ttft is None:
            self._ttft = self._elapsed_ms()

    def finish(self) -> dict | None:
        if not self._active:
            return None
        self._active = False
        return {
            "turn": self.turns,
            "ttfa_ms": self._ttfa,
            "ttft_ms": self._ttft,
            # Configured VAD silence, only for voice turns: perceived latency = ttfa_ms + vad_silence_ms.
            "vad_silence_ms": self._vad_silence_ms if self._kind == "voice" else None,
        }


def append_jsonl(path: Path, session_id: str, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "session_id": session_id,
        "turn": record.get("turn"),
        "ttfa_ms": record.get("ttfa_ms"),
        "ttft_ms": record.get("ttft_ms"),
        "vad_silence_ms": record.get("vad_silence_ms"),
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
