"""Config defaults (no .env read: load_env is stubbed out)."""
from app import config


def test_demo_safe_cap_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.delenv("MAX_SESSION_SECONDS", raising=False)
    monkeypatch.delenv("IDLE_TIMEOUT_SECONDS", raising=False)
    s = config.get_settings()
    assert s.max_session_seconds == 720
    assert s.idle_timeout_seconds == 90
    assert config.Settings().max_session_seconds == 720
    assert config.Settings().idle_timeout_seconds == 90


def test_cap_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.setenv("MAX_SESSION_SECONDS", "60")
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "10")
    s = config.get_settings()
    assert (s.max_session_seconds, s.idle_timeout_seconds) == (60, 10)
