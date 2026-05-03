"""Tests for Day 2: URL-spec helpers, squad endpoints, election info."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# --- URL-spec helpers ----------------------------------------------------

def test_calendar_event_url(app_mod):
    url = app_mod.calendar_event_url(
        title="Vote Day", start="2026-05-15",
        details="Polling open 7am–6pm", location="Chennai Central",
    )
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert "action=TEMPLATE" in url
    assert "Vote+Day" in url or "Vote%20Day" in url
    assert "20260515" in url  # date present in calendar format


def test_calendar_with_explicit_end(app_mod):
    url = app_mod.calendar_event_url(
        title="X", start="2026-01-01T08:00:00+05:30", end="2026-01-01T10:00:00+05:30",
    )
    # urlencode replaces "/" with %2F — both dates should be present in the encoded form
    assert "20260101T023000Z" in url
    assert "20260101T043000Z" in url
    assert "%2F" in url  # the slash separator between start and end


def test_whatsapp_share_url(app_mod):
    url = app_mod.whatsapp_share_url("hello world")
    assert url == "https://wa.me/?text=hello%20world"


def test_maps_search_url(app_mod):
    url = app_mod.maps_search_url("Chennai Central")
    assert url == "https://maps.google.com/?q=Chennai%20Central"


def test_eci_registration_url(app_mod):
    assert app_mod.eci_registration_url() == "https://electoralsearch.eci.gov.in/"


# --- Squad endpoints ------------------------------------------------------

def _create_payload():
    return {
        "name": "Family", "creator": "Shubham",
        "state": "TAMIL NADU", "constituency": "CHENNAI CENTRAL",
        "polling_date": "2026-05-15",
    }


def test_squad_create_missing_fields(client):
    r = client.post("/api/squad", json={"name": "X"})
    assert r.status_code == 400


def test_squad_create_and_get(client):
    r = client.post("/api/squad", json=_create_payload())
    assert r.status_code == 201
    body = r.get_json()
    assert "squad_id" in body
    assert body["join_url"].endswith("/squad/" + body["squad_id"])
    assert "wa.me" in body["whatsapp_share_url"]

    sid = body["squad_id"]
    r2 = client.get(f"/api/squad/{sid}")
    assert r2.status_code == 200
    body2 = r2.get_json()
    assert body2["name"] == "Family"
    assert "calendar.google.com" in body2["calendar_url"]
    assert "maps.google.com" in body2["maps_url"]
    assert len(body2["members"]) == 1


def test_squad_get_unknown(client):
    r = client.get("/api/squad/nonexistent")
    assert r.status_code == 404


def test_squad_page_renders(client):
    r = client.post("/api/squad", json=_create_payload())
    sid = r.get_json()["squad_id"]
    page = client.get(f"/squad/{sid}")
    assert page.status_code == 200
    assert b"Family" in page.data
    assert b"Add to Google Calendar" in page.data


def test_squad_page_not_found(client):
    page = client.get("/squad/nope-xyz")
    assert page.status_code == 404
    assert b"Squad not found" in page.data


def test_squad_join_and_checkin(client):
    r = client.post("/api/squad", json=_create_payload())
    sid = r.get_json()["squad_id"]

    join = client.post(f"/api/squad/{sid}/join", json={"name": "Priya"})
    assert join.status_code == 200
    assert len(join.get_json()["members"]) == 2

    # duplicate join
    dup = client.post(f"/api/squad/{sid}/join", json={"name": "priya"})
    assert dup.status_code == 409

    # missing name
    bad = client.post(f"/api/squad/{sid}/join", json={})
    assert bad.status_code == 400

    # checkin
    ci = client.post(f"/api/squad/{sid}/checkin", json={
        "name": "Priya", "registered": True, "researched": True,
    })
    assert ci.status_code == 200
    member = ci.get_json()["member"]
    assert member["registered"] is True
    assert member["researched"] is True
    assert member["voted"] is False


def test_squad_checkin_unknown_member(client):
    r = client.post("/api/squad", json=_create_payload())
    sid = r.get_json()["squad_id"]
    bad = client.post(f"/api/squad/{sid}/checkin", json={"name": "ghost", "voted": True})
    assert bad.status_code == 404


def test_squad_checkin_missing_data(client):
    r = client.post("/api/squad", json=_create_payload())
    sid = r.get_json()["squad_id"]
    bad = client.post(f"/api/squad/{sid}/checkin", json={"name": "Shubham"})
    assert bad.status_code == 400


def test_squad_checkin_unknown_squad(client):
    r = client.post("/api/squad/missing/checkin", json={"name": "x", "voted": True})
    assert r.status_code == 404


def test_squad_join_unknown(client):
    r = client.post("/api/squad/missing/join", json={"name": "x"})
    assert r.status_code == 404


# --- Election info --------------------------------------------------------

def test_election_info_missing_state(client):
    r = client.get("/api/election-info")
    assert r.status_code == 400


def test_election_info_demo_mode(app_mod, client, monkeypatch):
    monkeypatch.setattr(app_mod, "DEMO_MODE", True)
    r = client.get("/api/election-info?state=TAMIL+NADU")
    assert r.status_code == 200
    body = r.get_json()
    assert "summary" in body
    assert body["demo"] is True


def test_election_info_grounded(app_mod, client, monkeypatch):
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Tamil Nadu Lok Sabha 2024 polled on April 19."}]},
            "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://eci.gov.in/foo", "title": "ECI"}},
                {"web": {"uri": "https://example.org", "title": "Example"}},
            ]},
        }]
    }
    # bypass the cache
    monkeypatch.setattr(app_mod, "ELECTION_CACHE", {})
    with patch.object(app_mod.requests, "post", return_value=fake):
        r = client.get("/api/election-info?state=TAMIL+NADU&lang=en")
    assert r.status_code == 200
    body = r.get_json()
    assert "April 19" in body["summary"]
    assert len(body["citations"]) == 2
    assert body["citations"][0]["url"].startswith("https://")


def test_election_info_cached(app_mod, client, monkeypatch):
    import time as time_mod
    monkeypatch.setattr(app_mod, "ELECTION_CACHE", {
        f"{app_mod._norm_key('KERALA')}::English": (time_mod.time() + 100, {
            "state": "KERALA", "summary": "cached", "citations": [], "registration_url": "x", "lang": "English",
        })
    })
    # patch requests so a network call would explode if hit
    with patch.object(app_mod.requests, "post", side_effect=AssertionError("should not call")):
        r = client.get("/api/election-info?state=KERALA&lang=en")
    assert r.status_code == 200
    assert r.get_json()["summary"] == "cached"


def test_to_calendar_format_handles_iso(app_mod):
    out = app_mod._to_calendar_format("2026-05-15T09:00:00+05:30")
    assert out == "20260515T033000Z"


def test_squads_persistence_roundtrip(app_mod, tmp_path, monkeypatch):
    fake_path = tmp_path / "squads.json"
    monkeypatch.setattr(app_mod, "SQUADS_PATH", fake_path)
    app_mod._save_squads({"abc": {"name": "X"}})
    assert app_mod._load_squads() == {"abc": {"name": "X"}}


def test_squads_load_when_absent(app_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "SQUADS_PATH", tmp_path / "does-not-exist.json")
    assert app_mod._load_squads() == {}
