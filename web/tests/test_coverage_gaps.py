"""Tests targeting the coverage gaps left by the feature suites.

Each test in here exists to push coverage to 100% — they cover error paths,
fallback branches, dispatcher edge cases, and middleware skip conditions
that the happy-path tests don't reach.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import requests as real_requests

# ---------------------------------------------------------------------------
# _fuzzy_find_candidate — empty input + no-overlap branches
# ---------------------------------------------------------------------------

def test_fuzzy_find_empty_name(app_mod):
    cand, state, const = app_mod._fuzzy_find_candidate("")
    assert cand is None and state == "" and const == ""


def test_fuzzy_find_no_match_above_threshold(app_mod):
    # A name with no overlap to any real candidate
    cand, _, _ = app_mod._fuzzy_find_candidate("Zxqvbnnmkpwrtl")
    assert cand is None


def test_fuzzy_find_skips_whitespace_only_candidate(app_mod, monkeypatch):
    """A candidate with only whitespace in name should hit the 'continue' branch
    in fuzzy match (cand_words is empty but fast-path doesn't trigger)."""
    fake_state = {"ZZ_FAKE_STATE": {"ZZ_FAKE": [
        {"name": "   ", "party": "X"},  # whitespace-only — fast path won't match
        {"name": "Pqxz Wvut", "party": "Y"},  # unique words for clean test
    ]}}
    monkeypatch.setitem(app_mod.CANDIDATES, "states",
                        {**app_mod.CANDIDATES["states"], **fake_state})
    cand, _, _ = app_mod._fuzzy_find_candidate("Pqxz Wvut")
    assert cand is not None
    assert cand["party"] == "Y"


# ---------------------------------------------------------------------------
# _call_gemini — 429 fallback to Flash-Lite
# ---------------------------------------------------------------------------

def test_call_gemini_429_fallback_succeeds(app_mod):
    """Flash returns 429 → retry on Flash-Lite → success."""
    flash_429 = MagicMock(status_code=429)
    flash_429.raise_for_status.side_effect = real_requests.HTTPError("429")
    lite_ok = MagicMock(status_code=200)
    lite_ok.raise_for_status = MagicMock()
    lite_ok.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({"k": "v"})}]}}]
    }
    with patch.object(app_mod.requests, "post", side_effect=[flash_429, lite_ok]):
        out = app_mod._call_gemini("hi", {"type": "object", "properties": {"k": {"type": "string"}}})
    assert out == {"k": "v"}


def test_call_gemini_no_fallback_when_already_lite(app_mod):
    """If we explicitly call Flash-Lite and it 429s, don't retry — just raise."""
    lite_429 = MagicMock(status_code=429)
    lite_429.raise_for_status.side_effect = real_requests.HTTPError("429 from lite")
    with patch.object(app_mod.requests, "post", return_value=lite_429):
        try:
            app_mod._call_gemini("hi", {"type": "object"}, model=app_mod.GEMINI_MODEL_FAST)
        except real_requests.HTTPError as e:
            assert "429" in str(e)


def test_call_gemini_no_fallback_when_disabled(app_mod):
    """fallback_on_429=False: even Flash 429 should raise without retry."""
    flash_429 = MagicMock(status_code=429)
    flash_429.raise_for_status.side_effect = real_requests.HTTPError("429")
    with patch.object(app_mod.requests, "post", return_value=flash_429) as mock_post:
        try:
            app_mod._call_gemini("hi", {"type": "object"}, fallback_on_429=False)
        except real_requests.HTTPError:
            pass
    assert mock_post.call_count == 1  # no retry


# ---------------------------------------------------------------------------
# Chat dispatcher: candidate_brief NON-DEMO success + timeout paths
# ---------------------------------------------------------------------------

def _intent(intent, params=None, reply="ok", needs_clarification=False):
    body = {"intent": intent, "reply": reply,
            "needs_clarification": needs_clarification, "params": params or {}}
    fake = MagicMock(status_code=200)
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]
    }
    return fake


def _gemini_brief_response(background="bg", assets="a", cases="c"):
    fake = MagicMock(status_code=200)
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "background": background, "disclosed_assets": assets, "pending_cases": cases,
        })}]}}]
    }
    return fake


def test_chat_candidate_brief_live_gemini(app_mod, client):
    """Non-DEMO_MODE: classifier + brief generation chained, both mocked."""
    classifier = _intent("candidate_brief",
                         params={"state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
                                 "candidate_name": "B. Parthasarathy"})
    brief = _gemini_brief_response(background="Live brief generated.")
    with patch.object(app_mod.requests, "post", side_effect=[classifier, brief]):
        r = client.post("/api/chat", json={"message": "tell me about B Parthasarathy"})
    body = r.get_json()
    assert body["card"]["type"] == "brief"
    assert body["card"]["data"]["background"] == "Live brief generated."
    assert body["card"]["data"]["source_url"]


def test_chat_candidate_brief_gemini_timeout(app_mod, client):
    """When the brief Gemini call times out, return canned brief with fallback_reason."""
    classifier = _intent("candidate_brief",
                         params={"state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
                                 "candidate_name": "B. Parthasarathy"})
    with patch.object(app_mod.requests, "post",
                      side_effect=[classifier, real_requests.Timeout()]):
        r = client.post("/api/chat", json={"message": "tell me about B Parthasarathy"})
    body = r.get_json()
    assert body["card"]["type"] == "brief"
    assert body["card"]["data"]["fallback_reason"] == "gemini_timeout"


# ---------------------------------------------------------------------------
# Chat dispatcher: election_info live (non-DEMO)
# ---------------------------------------------------------------------------

def test_chat_election_info_live(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "ELECTION_CACHE", {})
    classifier = _intent("election_info", params={"state": "TAMIL NADU"})
    grounded = MagicMock(status_code=200)
    grounded.raise_for_status = MagicMock()
    grounded.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Live election summary."}]},
            "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://eci.gov.in", "title": "ECI"}},
            ]},
        }]
    }
    with patch.object(app_mod.requests, "post", side_effect=[classifier, grounded]):
        r = client.post("/api/chat", json={"message": "when is tamil nadu election"})
    body = r.get_json()
    assert body["card"]["type"] == "election"
    assert "Live election summary" in body["card"]["data"]["summary"]


# ---------------------------------------------------------------------------
# Chat dispatcher: manifesto_diff live + cached + timeout
# ---------------------------------------------------------------------------

def _diff_gemini_response():
    fake = MagicMock(status_code=200)
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "issue": "Women's safety",
            "rows": [{"point": "X", "party_a_position": "A", "party_b_position": "B",
                      "party_a_page": 1, "party_b_page": 2}],
        })}]}}]
    }
    return fake


def test_chat_manifesto_diff_live(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    classifier = _intent("manifesto_diff",
                         params={"party_a": "dmk", "party_b": "bjp", "issue": "women_safety"})
    with patch.object(app_mod.requests, "post", side_effect=[classifier, _diff_gemini_response()]):
        r = client.post("/api/chat", json={"message": "compare dmk and bjp"})
    body = r.get_json()
    assert body["card"]["type"] == "diff"
    assert body["card"]["data"]["party_a_short"] == "DMK"


def test_chat_manifesto_diff_cached(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {
        "dmk|bjp|women_safety|en": {"rows": [{"point": "x"}], "issue": "Women's safety"}
    })
    classifier = _intent("manifesto_diff",
                         params={"party_a": "dmk", "party_b": "bjp", "issue": "women_safety"})
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat", json={"message": "compare dmk and bjp on women safety"})
    body = r.get_json()
    assert body["card"]["type"] == "diff"
    assert body["card"]["data"]["cached"] is True


def test_chat_manifesto_diff_gemini_timeout(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    classifier = _intent("manifesto_diff",
                         params={"party_a": "dmk", "party_b": "bjp", "issue": "women_safety"})
    with patch.object(app_mod.requests, "post",
                      side_effect=[classifier, real_requests.Timeout()]):
        r = client.post("/api/chat", json={"message": "compare dmk and bjp on women safety"})
    body = r.get_json()
    assert body["card"]["type"] == "diff"
    assert body["card"]["data"]["fallback_reason"] == "gemini_timeout"


# ---------------------------------------------------------------------------
# Chat: classifier needs_clarification override for candidate_brief
# ---------------------------------------------------------------------------

def test_chat_needs_clarification_override_for_brief(app_mod, client, monkeypatch):
    """Even if classifier sets needs_clarification=true, candidate_brief with a name
    should still dispatch (we override and try fuzzy search)."""
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    classifier = _intent("candidate_brief",
                         params={"candidate_name": "B. Parthasarathy"},
                         needs_clarification=True,
                         reply="Need state too?")
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat", json={"message": "tell me about Parthasarathy"})
    body = r.get_json()
    # Override should kick in, dispatch should produce a brief
    assert body["card"]["type"] == "brief"


# ---------------------------------------------------------------------------
# Chat: issue keyword backfill (when classifier omits issue)
# ---------------------------------------------------------------------------

def test_chat_diff_issue_backfilled_from_message(app_mod, client, monkeypatch):
    """Classifier omits issue; backfill scans the user message for keywords."""
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    classifier = _intent("manifesto_diff",
                         params={"party_a": "dmk", "party_b": "bjp"})  # no issue
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat",
                        json={"message": "compare DMK and BJP on women safety"})
    body = r.get_json()
    assert body["card"]["type"] == "diff"


def test_chat_diff_no_issue_in_message_or_params(app_mod, client, monkeypatch):
    """If neither classifier nor message mentions an issue, return error."""
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    monkeypatch.setattr(app_mod, "MANIFESTO_DIFF_CACHE", {})
    classifier = _intent("manifesto_diff",
                         params={"party_a": "dmk", "party_b": "bjp"})
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat", json={"message": "compare dmk and bjp"})
    assert "error" in r.get_json()


# ---------------------------------------------------------------------------
# Chat: classifier with prior conversation history (history block path)
# ---------------------------------------------------------------------------

def test_chat_with_history(app_mod, client):
    classifier = _intent("smalltalk", reply="Continuing our chat.")
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat", json={
            "message": "tell me more",
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
        })
    assert r.status_code == 200
    assert r.get_json()["intent"] == "smalltalk"


# ---------------------------------------------------------------------------
# api_candidates: unknown-state branch
# ---------------------------------------------------------------------------

def test_candidates_endpoint_unknown_state(client):
    """Direct /api/candidates with bad state hits the 'unknown state' branch."""
    r = client.get("/api/candidates?state=ATLANTIS&constituency=X")
    assert r.status_code == 404
    assert r.get_json()["error"] == "unknown state"


# ---------------------------------------------------------------------------
# Brief endpoint: Gemini error branches
# ---------------------------------------------------------------------------

def test_brief_endpoint_gemini_timeout(client, app_mod):
    with patch.object(app_mod.requests, "post", side_effect=real_requests.Timeout()):
        r = client.post("/api/brief", json={
            "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
            "name": "B. Parthasarathy", "lang": "en",
        })
    assert r.status_code == 200
    assert r.get_json()["fallback_reason"] == "gemini_timeout"


def test_brief_endpoint_gemini_other_error(client, app_mod):
    with patch.object(app_mod.requests, "post", side_effect=ValueError("boom")):
        r = client.post("/api/brief", json={
            "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
            "name": "B. Parthasarathy", "lang": "en",
        })
    assert r.status_code == 503
    assert "brief generation failed" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# gzip middleware — call the function directly (Flask doesn't allow runtime route adds)
# ---------------------------------------------------------------------------

def test_gzip_skipped_for_non_2xx(app_mod):
    from flask import Response
    with app_mod.app.test_request_context("/x", headers={"Accept-Encoding": "gzip"}):
        resp = Response(b"x" * 1000, status=302)
        out = app_mod.gzip_response(resp)
    assert out.headers.get("Content-Encoding") != "gzip"


def test_gzip_skipped_when_already_encoded(app_mod):
    from flask import Response
    with app_mod.app.test_request_context("/x", headers={"Accept-Encoding": "gzip"}):
        resp = Response(b"x" * 1000, status=200)
        resp.headers["Content-Encoding"] = "br"
        out = app_mod.gzip_response(resp)
    assert out.headers.get("Content-Encoding") == "br"


def test_gzip_skipped_for_direct_passthrough(app_mod):
    from flask import Response
    with app_mod.app.test_request_context("/x", headers={"Accept-Encoding": "gzip"}):
        resp = Response(b"x" * 1000, status=200)
        resp.direct_passthrough = True
        out = app_mod.gzip_response(resp)
    assert out.headers.get("Content-Encoding") != "gzip"


# ---------------------------------------------------------------------------
# Dispatcher: smalltalk path returns {} (line 722)
# ---------------------------------------------------------------------------

def test_dispatch_smalltalk_returns_empty(app_mod):
    out = app_mod._dispatch_intent("smalltalk", {}, "en")
    assert out == {}


def test_dispatch_unknown_returns_empty(app_mod):
    out = app_mod._dispatch_intent("unknown", {}, "en")
    assert out == {}


# ---------------------------------------------------------------------------
# Chat dispatcher: list_candidates with unknown state (line 618)
# ---------------------------------------------------------------------------

def test_chat_list_candidates_unknown_state(app_mod, client):
    classifier = _intent("list_candidates",
                         params={"state": "ATLANTIS", "constituency": "X"})
    with patch.object(app_mod.requests, "post", return_value=classifier):
        r = client.post("/api/chat", json={"message": "who's running in x"})
    body = r.get_json()
    assert "error" in body
    assert "ATLANTIS" in body["error"]


# ---------------------------------------------------------------------------
# Chat endpoint: connection error in classifier (line 748-749)
# ---------------------------------------------------------------------------

def test_chat_classifier_connection_error(app_mod, client):
    """Connection error path is distinct from Timeout — both should be handled."""
    with patch.object(app_mod.requests, "post", side_effect=real_requests.ConnectionError()):
        r = client.post("/api/chat", json={"message": "hi"})
    body = r.get_json()
    assert body["intent"] == "unknown"
    assert "couldn't reach" in body["reply"].lower()


# ---------------------------------------------------------------------------
# _get_election_info — Timeout/ConnectionError fallback
# ---------------------------------------------------------------------------

def test_get_election_info_timeout_fallback(app_mod, monkeypatch):
    """When the grounded Gemini call times out, return the canned 'check eci.gov.in' message."""
    monkeypatch.setattr(app_mod, "ELECTION_CACHE", {})
    with patch.object(app_mod.requests, "post", side_effect=real_requests.Timeout()):
        info = app_mod._get_election_info("KARNATAKA", "English")
    assert info["fallback"] == "gemini_timeout"
    assert "eci.gov.in" in info["summary"]


# ---------------------------------------------------------------------------
# _call_gemini_grounded — citation chunk without 'uri' should be skipped
# ---------------------------------------------------------------------------

def test_grounded_skips_chunk_without_uri(app_mod):
    fake = MagicMock(status_code=200)
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "summary"}]},
            "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://eci.gov.in", "title": "ECI"}},
                {"web": {}},  # no URI — should be skipped
                {"other": "shape"},  # no 'web' field at all
            ]},
        }]
    }
    with patch.object(app_mod.requests, "post", return_value=fake):
        text, citations = app_mod._call_gemini_grounded("test")
    assert text == "summary"
    assert len(citations) == 1
    assert citations[0]["url"] == "https://eci.gov.in"


# ---------------------------------------------------------------------------
# _manifesto_text — empty page text should be skipped (no [PAGE N] marker)
# ---------------------------------------------------------------------------

def test_manifesto_text_skips_empty_pages(app_mod, monkeypatch):
    fake_party = {"pages": ["", "real content", "", "more content"]}
    monkeypatch.setitem(app_mod.MANIFESTOS["parties"], "test_party", fake_party)
    text = app_mod._manifesto_text("test_party")
    assert "[PAGE 2]" in text  # second page is non-empty → has marker
    assert "[PAGE 4]" in text
    assert "[PAGE 1]" not in text  # empty pages skipped (no markers)
    assert "[PAGE 3]" not in text


# ---------------------------------------------------------------------------
# gzip middleware — Accept-Encoding header missing entirely (line 1155)
# ---------------------------------------------------------------------------

def test_gzip_skipped_when_no_accept_encoding(app_mod):
    from flask import Response
    with app_mod.app.test_request_context("/x"):  # no Accept-Encoding header
        resp = Response(b"x" * 1000, status=200)
        out = app_mod.gzip_response(resp)
    assert out.headers.get("Content-Encoding") != "gzip"


def test_gzip_skipped_when_response_too_small(app_mod):
    from flask import Response
    with app_mod.app.test_request_context("/x", headers={"Accept-Encoding": "gzip"}):
        resp = Response(b"x" * 100, status=200)  # < 500 byte threshold
        out = app_mod.gzip_response(resp)
    assert out.headers.get("Content-Encoding") != "gzip"
