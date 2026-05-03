"""Smoke tests for app endpoints. Mocks all Gemini calls."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["candidates_loaded"] > 0
    assert body["states"] > 0


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Matdaan Mitra" in r.data


def test_states_endpoint(client):
    r = client.get("/api/states")
    assert r.status_code == 200
    body = r.get_json()
    assert "TAMIL NADU" in body["states"]
    assert body["count"] == len(body["states"])


def test_constituencies_endpoint(client):
    r = client.get("/api/constituencies?state=TAMIL+NADU")
    assert r.status_code == 200
    assert "CHENNAI CENTRAL" in r.get_json()["constituencies"]


def test_constituencies_unknown_state(client):
    r = client.get("/api/constituencies?state=NOT+A+STATE")
    assert r.status_code == 404


def test_candidates_endpoint(client):
    r = client.get("/api/candidates?state=TAMIL+NADU&constituency=CHENNAI+CENTRAL")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["candidates"]) > 0
    assert "source_url" in body


def test_candidates_unknown_constituency(client):
    r = client.get("/api/candidates?state=TAMIL+NADU&constituency=NOT+REAL")
    assert r.status_code == 404


def test_brief_missing_fields(client):
    r = client.post("/api/brief", json={"state": "TAMIL NADU"})
    assert r.status_code == 400


def test_brief_unknown_candidate(client):
    r = client.post("/api/brief", json={
        "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL", "name": "Nobody",
    })
    assert r.status_code == 404


def test_brief_demo_mode(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    r = client.post("/api/brief", json={
        "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
        "name": "B. Parthasarathy", "lang": "en",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["demo"] is True
    assert "criminal case" in body["pending_cases"].lower()


def test_brief_with_gemini_mocked(app_mod, client):
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "background": "Mocked background.",
            "disclosed_assets": "Mocked assets.",
            "pending_cases": "Mocked cases.",
        })}]}}]
    }
    with patch.object(app_mod.requests, "post", return_value=fake_response):
        r = client.post("/api/brief", json={
            "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
            "name": "B. Parthasarathy", "lang": "en",
        })
    assert r.status_code == 200
    body = r.get_json()
    assert body["background"] == "Mocked background."
    assert body["candidate"] == "B. Parthasarathy"


def test_gzip_middleware(client):
    # Hit a >500-byte endpoint so the gzip threshold engages.
    r = client.get(
        "/api/candidates?state=TAMIL+NADU&constituency=CHENNAI+CENTRAL",
        headers={"Accept-Encoding": "gzip"},
    )
    assert r.status_code == 200
    assert r.headers.get("Content-Encoding") == "gzip"


def test_gzip_skipped_when_not_accepted(client):
    r = client.get("/api/states")  # no Accept-Encoding header
    assert r.status_code == 200
    assert r.headers.get("Content-Encoding") is None


def test_norm_key(app_mod):
    assert app_mod._norm_key("  tamil   nadu  ") == "TAMIL NADU"


def test_resolve_lang(app_mod):
    assert app_mod._resolve_lang("en") == "English"
    assert "Hindi" in app_mod._resolve_lang("hi")
    assert app_mod._resolve_lang("xx") == "xx"  # passthrough for unknown
    assert app_mod._resolve_lang(None) == "English"


def test_find_candidate(app_mod):
    c = app_mod._find_candidate("TAMIL NADU", "CHENNAI CENTRAL", "B. Parthasarathy")
    assert c is not None
    assert c["party"] == "DMDK"
    assert app_mod._find_candidate("TAMIL NADU", "CHENNAI CENTRAL", "ghost") is None
    assert app_mod._find_candidate("nope", "x", "y") is None
    assert app_mod._find_candidate("TAMIL NADU", "nope", "y") is None
