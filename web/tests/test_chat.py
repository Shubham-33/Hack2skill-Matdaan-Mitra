"""Tests for the /api/chat endpoint and intent dispatcher."""

from __future__ import annotations

import json
from unittest.mock import patch

# --- Suggestions ----------------------------------------------------------

def test_suggestions_default(client):
    r = client.get("/api/suggestions")
    assert r.status_code == 200
    items = r.get_json()["suggestions"]
    assert len(items) >= 4
    assert any("DMK" in s or "BJP" in s for s in items)


def test_suggestions_hindi(client):
    r = client.get("/api/suggestions?lang=hi")
    assert r.status_code == 200
    items = r.get_json()["suggestions"]
    # at least one should contain Devanagari
    assert any(any("ऀ" <= ch <= "ॿ" for ch in s) for s in items)


# --- /api/chat — input validation -----------------------------------------

def test_chat_requires_message(client):
    r = client.post("/api/chat", json={})
    assert r.status_code == 400


# --- Helpers --------------------------------------------------------------

def _intent_response(intent, params=None, reply="ok", needs_clarification=False):
    """Wrap an intent classifier output as a fake Gemini response."""
    body = {
        "intent": intent,
        "reply": reply,
        "needs_clarification": needs_clarification,
        "params": params or {},
    }
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]
    }
    return fake


# --- Smalltalk path -------------------------------------------------------

def test_chat_smalltalk(app_mod, client):
    fake = _intent_response("smalltalk", reply="Namaste! How can I help?")
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "hi", "lang": "en"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["intent"] == "smalltalk"
    assert body["reply"].startswith("Namaste")
    assert "card" not in body


def test_chat_help(app_mod, client):
    fake = _intent_response("help", reply="I can find candidates, election dates, manifestos.")
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "what can you do?", "lang": "en"})
    assert r.status_code == 200
    assert r.get_json()["intent"] == "help"


# --- Clarification --------------------------------------------------------

def test_chat_needs_clarification(app_mod, client):
    fake = _intent_response("candidate_brief", reply="Which candidate?", needs_clarification=True)
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "tell me about a candidate"})
    body = r.get_json()
    assert body["needs_clarification"] is True
    assert "card" not in body


# --- list_constituencies dispatch ----------------------------------------

def test_chat_list_constituencies_known_state(app_mod, client):
    fake = _intent_response("list_constituencies", params={"state": "TAMIL NADU"})
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "constituencies in tamil nadu"})
    body = r.get_json()
    assert body["card"]["type"] == "constituencies"
    assert "CHENNAI CENTRAL" in body["card"]["constituencies"]


def test_chat_list_constituencies_unknown_state(app_mod, client):
    fake = _intent_response("list_constituencies", params={"state": "ATLANTIS"})
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "constituencies in atlantis"})
    assert "error" in r.get_json()


# --- list_candidates ------------------------------------------------------

def test_chat_list_candidates(app_mod, client):
    fake = _intent_response("list_candidates",
                            params={"state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL"})
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "who's running in chennai central"})
    body = r.get_json()
    assert body["card"]["type"] == "candidates"
    assert len(body["card"]["candidates"]) > 0


def test_chat_list_candidates_unknown_constituency(app_mod, client):
    fake = _intent_response("list_candidates",
                            params={"state": "TAMIL NADU", "constituency": "NOT REAL"})
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.post("/api/chat", json={"message": "who's running in not real"})
    assert "error" in r.get_json()


# --- candidate_brief: includes a second Gemini call (the brief itself) ---

def test_chat_candidate_brief_demo_mode(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    fake_intent = _intent_response("candidate_brief",
                                   params={"state": "TAMIL NADU",
                                           "constituency": "CHENNAI CENTRAL",
                                           "candidate_name": "B. Parthasarathy"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "tell me about B Parthasarathy"})
    body = r.get_json()
    assert body["card"]["type"] == "brief"
    assert body["card"]["candidate"] == "B. Parthasarathy"
    assert body["card"]["data"]["demo"] is True


def test_chat_candidate_brief_name_only_searches(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    fake_intent = _intent_response("candidate_brief",
                                   params={"candidate_name": "Parthasarathy"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "tell me about Parthasarathy"})
    body = r.get_json()
    # Should find via name search across all constituencies
    assert body["card"]["type"] == "brief"


def test_chat_candidate_not_found(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    fake_intent = _intent_response("candidate_brief",
                                   params={"candidate_name": "GhostNobodyEver"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "tell me about GhostNobodyEver"})
    body = r.get_json()
    assert "error" in body


# --- election_info --------------------------------------------------------

def test_chat_election_info_demo(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    fake_intent = _intent_response("election_info", params={"state": "TAMIL NADU"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "when is tamil nadu election"})
    body = r.get_json()
    assert body["card"]["type"] == "election"
    assert body["card"]["data"]["demo"] is True


def test_chat_election_info_missing_state(app_mod, client):
    fake_intent = _intent_response("election_info", params={})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "when is the election"})
    assert "error" in r.get_json()


# --- manifesto_diff -------------------------------------------------------

def test_chat_manifesto_diff_demo(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    fake_intent = _intent_response("manifesto_diff",
                                   params={"party_a": "dmk", "party_b": "bjp",
                                           "issue": "women_safety"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "compare dmk and bjp on women safety"})
    body = r.get_json()
    assert body["card"]["type"] == "diff"
    assert body["card"]["data"]["demo"] is True


def test_chat_manifesto_diff_unknown_party(app_mod, client):
    fake_intent = _intent_response("manifesto_diff",
                                   params={"party_a": "ghost", "party_b": "bjp",
                                           "issue": "women_safety"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "compare ghost and bjp"})
    assert "error" in r.get_json()


def test_chat_manifesto_diff_unknown_issue(app_mod, client):
    fake_intent = _intent_response("manifesto_diff",
                                   params={"party_a": "dmk", "party_b": "bjp",
                                           "issue": "weather"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "compare on weather"})
    assert "error" in r.get_json()


# --- create_squad ---------------------------------------------------------

def test_chat_create_squad(app_mod, client):
    fake_intent = _intent_response("create_squad",
                                   params={"squad_name": "Family", "state": "TAMIL NADU",
                                           "constituency": "CHENNAI CENTRAL",
                                           "polling_date": "2026-05-15",
                                           "creator_name": "Shubham"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "create a squad called Family for me in Chennai Central, polling 2026-05-15"})
    body = r.get_json()
    assert body["card"]["type"] == "squad"
    assert body["card"]["data"]["name"] == "Family"


def test_chat_create_squad_missing_fields(app_mod, client):
    fake_intent = _intent_response("create_squad", params={"squad_name": "X"})
    with patch.object(app_mod.requests, "post", return_value=fake_intent):
        r = client.post("/api/chat", json={"message": "make a squad"})
    body = r.get_json()
    assert "error" in body
    assert "I need" in body["error"]


# --- Resilience -----------------------------------------------------------

def test_chat_classifier_timeout(app_mod, client):
    import requests as real_requests
    with patch.object(app_mod.requests, "post", side_effect=real_requests.Timeout()):
        r = client.post("/api/chat", json={"message": "hello"})
    body = r.get_json()
    assert body["intent"] == "unknown"
    assert "couldn't reach" in body["reply"].lower()


def test_chat_classifier_other_error(app_mod, client):
    with patch.object(app_mod.requests, "post", side_effect=ValueError("boom")):
        r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 503
