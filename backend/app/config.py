"""Settings from backend/.env (python-dotenv). Values are never printed or logged."""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"
DEFAULT_LATENCY_LOG = BACKEND_DIR / "logs" / "latency.jsonl"

log = logging.getLogger("medvox.config")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default="", repr=False)
    realtime_model: str = ""
    transcribe_model: str = ""
    max_session_seconds: float = 240
    idle_timeout_seconds: float = 45
    max_output_tokens: int = 150
    vad_threshold: float = 0.5
    vad_silence_ms: int = 500
    vad_prefix_padding_ms: int = 300
    # Lowest documented effort; "none" omits the field for models without reasoning.
    reasoning_effort: str | None = "minimal"
    latency_log_path: Path = DEFAULT_LATENCY_LOG

    @property
    def upstream_configured(self) -> bool:
        return bool(self.openai_api_key and self.realtime_model)


def load_env() -> None:
    load_dotenv(ENV_PATH, override=False)


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def _num(name: str, default, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        log.warning("invalid number in %s, using default", name)  # name only, never the value
        return default


def get_settings() -> Settings:
    load_env()
    effort = _str("REASONING_EFFORT", "minimal")
    return Settings(
        openai_api_key=_str("OPENAI_API_KEY"),
        realtime_model=_str("REALTIME_MODEL"),
        transcribe_model=_str("TRANSCRIBE_MODEL"),
        max_session_seconds=_num("MAX_SESSION_SECONDS", 240, float),
        idle_timeout_seconds=_num("IDLE_TIMEOUT_SECONDS", 45, float),
        max_output_tokens=_num("MAX_OUTPUT_TOKENS", 150, int),
        vad_threshold=_num("VAD_THRESHOLD", 0.5, float),
        vad_silence_ms=_num("VAD_SILENCE_MS", 500, int),
        vad_prefix_padding_ms=_num("VAD_PREFIX_PADDING_MS", 300, int),
        reasoning_effort=None if effort.lower() == "none" else effort,
        latency_log_path=Path(_str("LATENCY_LOG_PATH")) if _str("LATENCY_LOG_PATH") else DEFAULT_LATENCY_LOG,
    )
