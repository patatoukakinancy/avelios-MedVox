"""CORS for REST routes. No network."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import DEFAULT_CORS_ORIGINS, parse_cors_origins

BAD = "http://evil.example"


def test_defaults_when_unset_or_empty():
    assert parse_cors_origins(None) == list(DEFAULT_CORS_ORIGINS)
    assert parse_cors_origins("") == list(DEFAULT_CORS_ORIGINS)
    assert parse_cors_origins(" , ") == list(DEFAULT_CORS_ORIGINS)
    assert "http://localhost:5173" in DEFAULT_CORS_ORIGINS


def test_parse_custom_strips_and_drops_wildcard():
    assert parse_cors_origins(" http://a.test:1/ ,http://b.test ") == ["http://a.test:1", "http://b.test"]
    assert parse_cors_origins("*") == list(DEFAULT_CORS_ORIGINS)
    assert parse_cors_origins("*,http://a.test") == ["http://a.test"]


def test_app_never_allows_wildcard():
    assert "*" not in main.CORS_ORIGINS and main.CORS_ORIGINS


def test_get_with_allowed_origin():
    origin = main.CORS_ORIGINS[0]
    res = TestClient(main.app).get("/patients", headers={"Origin": origin})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == origin


def test_get_with_disallowed_origin():
    res = TestClient(main.app).get("/patients", headers={"Origin": BAD})
    assert res.status_code == 200
    assert "access-control-allow-origin" not in res.headers


def test_preflight_allowed_and_disallowed():
    client = TestClient(main.app)
    headers = {"Access-Control-Request-Method": "GET"}
    ok = client.options("/patients", headers={"Origin": main.CORS_ORIGINS[0], **headers})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == main.CORS_ORIGINS[0]
    bad = client.options("/patients", headers={"Origin": BAD, **headers})
    assert "access-control-allow-origin" not in bad.headers
