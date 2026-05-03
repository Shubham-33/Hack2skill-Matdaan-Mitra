"""Tests for Day 3: Manifesto Diff endpoint + parties listing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_parties_endpoint(client):
    r = client.get("/api/parties")
    assert r.status_code == 200
    body = r.get_json()
    slugs = {p["slug"] for p in body["parties"]}
    assert {"bjp", "inc", "dmk", "cpim"}.issubset(slugs)
    assert any(i["key"] == "women_safety" for i in body["issues"])
    assert body["source_url"]


def test_diff_missing_fields(client):
    r = client.post("/api/manifesto-diff", json={"a": "bjp"})
    assert r.status_code == 400


def test_diff_same_party(client):
    r = client.post("/api/manifesto-diff", json={"a": "bjp", "b": "bjp", "issue": "jobs"})
    assert r.status_code == 400


def test_diff_unknown_party(client):
    r = client.post("/api/manifesto-diff", json={"a": "ghost", "b": "bjp", "issue": "jobs"})
    assert r.status_code == 404


def test_diff_unknown_issue(client):
    r = client.post("/api/manifesto-diff", json={"a": "bjp", "b": "inc", "issue": "weather"})
    assert r.status_code == 400


def test_diff_demo_mode(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    r = client.post("/api/manifesto-diff", json={
        "a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["demo"] is True
    assert len(body["rows"]) >= 3
    assert "DMK" in body["rows"][0]["party_a_position"]
    assert "BJP" in body["rows"][0]["party_b_position"]


def test_diff_demo_mode_caches(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    body = {"a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en"}
    client.post("/api/manifesto-diff", json=body)
    r2 = client.post("/api/manifesto-diff", json=body)
    assert r2.get_json().get("cached") is True


def test_diff_with_gemini_mocked(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "issue": "Women's safety",
            "rows": [
                {
                    "point": "Cash transfers",
                    "party_a_position": "DMK promises X.",
                    "party_a_page": 5,
                    "party_b_position": "BJP promises Y.",
                    "party_b_page": 12,
                },
            ],
        })}]}}]
    }
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/manifesto-diff", json={
            "a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en",
        })
    assert r.status_code == 200
    body = r.get_json()
    assert body["party_a_short"] == "DMK"
    assert body["party_b_short"] == "BJP"
    assert body["rows"][0]["party_a_page"] == 5


def test_diff_gemini_timeout_falls_back(app_mod, client, monkeypatch):
    import requests as real_requests
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    with patch.object(app_mod.requests, "post", side_effect=real_requests.Timeout()):
        r = client.post("/api/manifesto-diff", json={
            "a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en",
        })
    assert r.status_code == 200
    body = r.get_json()
    assert body["fallback_reason"] == "gemini_timeout"
    assert "rows" in body


def test_diff_gemini_other_error(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    with patch.object(app_mod.requests, "post", side_effect=ValueError("boom")):
        r = client.post("/api/manifesto-diff", json={
            "a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en",
        })
    assert r.status_code == 503
    assert "diff generation failed" in r.get_json()["error"]


def test_manifesto_text_helper(app_mod):
    text = app_mod._manifesto_text("dmk", max_pages=3)
    assert "[PAGE 1]" in text


def test_manifesto_text_unknown_party(app_mod):
    assert app_mod._manifesto_text("ghost") == ""


def test_load_manifestos_when_absent(app_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTOS_PATH", tmp_path / "no.json")
    out = app_mod._load_manifestos()
    assert out["parties"] == {}
