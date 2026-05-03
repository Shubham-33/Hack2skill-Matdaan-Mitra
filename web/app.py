"""Matdaan Mitra — Flask app.

A multilingual Indian election companion. See directives/build_matdaan_mitra.md
for the full plan.

Endpoints:
    GET  /                                                Index page (4 feature tiles)
    GET  /api/states                                      List of states with candidate data
    GET  /api/constituencies?state=...                    Constituencies for a state
    GET  /api/candidates?state=...&constituency=...       Candidates in a constituency
    POST /api/brief                                       Gemini-generated 3-bullet brief
    GET  /api/election-info?state=...&lang=...            Election dates + ECI links
    POST /api/squad                                       Create a Voting Squad
    GET  /squad/<squad_id>                                Squad join page (HTML)
    POST /api/squad/<squad_id>/join                       Add member to squad
    POST /api/squad/<squad_id>/checkin                    Update member checkbox state
    GET  /api/squad/<squad_id>                            Get squad state (JSON)
    GET  /api/health                                      Liveness probe
"""

from __future__ import annotations

import gzip
import json
import os
import re
import secrets
import time
import urllib.parse as urllib_parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    make_response,
    render_template,
    request,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

APP_DIR: Final[Path] = Path(__file__).resolve().parent
CANDIDATES_PATH: Final[Path] = APP_DIR / "data" / "candidates.json"
SQUADS_PATH: Final[Path] = APP_DIR / "data" / "squads.json"
MANIFESTOS_PATH: Final[Path] = APP_DIR / "data" / "manifestos.json"

ELECTION_INFO_TTL_S: Final[int] = 60 * 60  # 1 hour cache for grounded election dates

ISSUES: Final[dict[str, str]] = {
    "women_safety": "Women's safety and gender equality",
    "jobs": "Employment and economy",
    "education": "Education and schools",
    "healthcare": "Healthcare and medical access",
    "climate": "Climate, environment and energy",
    "farmers": "Farmers and rural welfare",
    "youth": "Youth, sports and skill development",
}

GEMINI_API_KEY: Final[str] = os.environ.get("GOOGLE_AI_API_KEY", "")
GEMINI_MODEL: Final[str] = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL: Final[str] = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
GEMINI_TIMEOUT_S: Final[int] = 12
DEMO_MODE: Final[bool] = os.environ.get("DEMO_MODE", "").lower() in {"1", "true", "yes"}

# Cache-bust static assets per playbook. Use file mtime when meaningful (local dev),
# fall back to module-load time (Cloud Run buildpacks reset mtime → epoch, so we'd
# never bust the cache between deploys). Module-load time changes per container start,
# which means every new deploy gets a fresh build_id.
def _compute_build_id() -> str:
    mtime = int(APP_DIR.joinpath("app.py").stat().st_mtime)
    if mtime < 1_000_000_000:  # < 2001 ⇒ epoch reset (Cloud Build buildpacks)
        return str(int(time.time()))
    return str(mtime)


BUILD_ID: Final[str] = _compute_build_id()

SUPPORTED_LANGS: Final[dict[str, str]] = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "ta": "Tamil (தமிழ்)",
    "bn": "Bengali (বাংলা)",
    "mr": "Marathi (मराठी)",
}

# ---------------------------------------------------------------------------
# Data load (eager — file is < 1 MB)
# ---------------------------------------------------------------------------

with CANDIDATES_PATH.open(encoding="utf-8") as _f:
    CANDIDATES: Final[dict] = json.load(_f)


def _load_squads() -> dict:
    if SQUADS_PATH.exists():
        return json.loads(SQUADS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_squads(squads: dict) -> None:
    SQUADS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQUADS_PATH.write_text(json.dumps(squads, ensure_ascii=False, indent=2), encoding="utf-8")


SQUADS: dict = _load_squads()  # in-memory mutable; persisted on each write
ELECTION_CACHE: dict[str, tuple[float, dict]] = {}  # state → (expires_at, payload)


def _load_manifestos() -> dict:
    if MANIFESTOS_PATH.exists():
        return json.loads(MANIFESTOS_PATH.read_text(encoding="utf-8"))
    return {"parties": {}, "source": "", "source_url": ""}


MANIFESTOS: Final[dict] = _load_manifestos()
MANIFESTO_DIFF_CACHE: dict[str, dict] = {}  # (a,b,issue,lang) → payload

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24  # 1-day cache for static


@app.context_processor
def _inject_globals() -> dict:
    return {"build_id": BUILD_ID, "langs": SUPPORTED_LANGS}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _norm_key(value: str) -> str:
    """Normalize state/constituency for lookup."""
    return " ".join(value.strip().upper().split())


def _find_candidate(state: str, constituency: str, name: str) -> dict | None:
    """Locate a candidate dict by triple. Case/space insensitive."""
    s = CANDIDATES["states"].get(_norm_key(state)) if state else None
    if not s:
        return None
    cands = s.get(_norm_key(constituency)) if constituency else None
    if not cands:
        return None
    target = re.sub(r"\s+", "", name).lower()
    for c in cands:
        if re.sub(r"\s+", "", c["name"]).lower() == target:
            return c
    return None


def _fuzzy_find_candidate(name: str) -> tuple[dict | None, str, str]:
    """Search the whole dataset for the best name match. Returns (candidate, state, constituency).

    Uses word-set overlap as primary signal (handles truncation/typos in either direction)
    plus a substring check as a fast path. None if nothing meaningful matches.
    """
    needle_words = set(name.lower().split())
    if not needle_words:
        return None, "", ""

    best: tuple[float, dict | None, str, str] = (0.0, None, "", "")
    for s_key, consts in CANDIDATES["states"].items():
        for c_key, cands in consts.items():
            for c in cands:
                cand_lower = c["name"].lower()
                # Fast path: either side substring (handles "Dayanidhi Maran" vs "Dayanidhi Mara")
                if name.lower() in cand_lower or cand_lower in name.lower():
                    return c, s_key, c_key
                # Fuzzy: Jaccard-ish overlap of word sets (handles word reorderings + truncations)
                cand_words = set(cand_lower.split())
                if not cand_words:
                    continue
                overlap = len(needle_words & cand_words) / max(len(needle_words), len(cand_words))
                if overlap > best[0]:
                    best = (overlap, c, s_key, c_key)

    return (best[1], best[2], best[3]) if best[0] >= 0.5 else (None, "", "")


def _resolve_lang(code: str | None) -> str:
    """Return the language *name* for prompting Gemini. Unknown → still passed through."""
    if not code:
        return SUPPORTED_LANGS["en"]
    return SUPPORTED_LANGS.get(code, code)  # let Gemini handle non-listed Indian langs


def _brief_prompt(candidate: dict, state: str, constituency: str, lang_name: str) -> str:
    """Build the prompt for the candidate brief. Neutral framing, no editorialization."""
    return (
        f"You are a neutral civic-information assistant. Write a 3-bullet brief about a "
        f"Lok Sabha 2024 candidate using ONLY the facts provided. Do not add any information "
        f"not in the facts. Frame any criminal cases as 'declared in 2024 affidavit' — never "
        f"as 'convicted' or 'criminal'. Output language: {lang_name}.\n\n"
        f"FACTS:\n"
        f"- Name: {candidate['name']}\n"
        f"- Party: {candidate['party']}\n"
        f"- Constituency: {constituency} ({state})\n"
        f"- Age: {candidate.get('age', 'not disclosed')}\n"
        f"- Education: {candidate.get('education', 'not disclosed')}\n"
        f"- Total assets (INR): {candidate.get('total_assets_inr', 'not disclosed')}\n"
        f"- Liabilities (INR): {candidate.get('liabilities_inr', 'not disclosed')}\n"
        f"- Criminal cases declared in 2024 affidavit: {candidate.get('criminal_cases', 0)}\n"
        f"- Won 2024 Lok Sabha seat: {'Yes' if candidate.get('winner') else 'No'}\n\n"
        f"Return JSON matching the schema."
    )


_BRIEF_SCHEMA: Final[dict] = {
    "type": "object",
    "properties": {
        "background": {"type": "string", "description": "Age, education, party affiliation in one sentence"},
        "disclosed_assets": {"type": "string", "description": "Asset and liability figures in INR, formatted readably"},
        "pending_cases": {"type": "string", "description": "Criminal cases as filed in affidavit; if 0, say so plainly"},
    },
    "required": ["background", "disclosed_assets", "pending_cases"],
}


def _canned_brief(candidate: dict, lang: str) -> dict:
    """Demo-mode brief — instant, no Gemini call."""
    return {
        "background": f"{candidate['name']} ({candidate['party']}), age {candidate.get('age', '—')}, education: {candidate.get('education', '—')}.",
        "disclosed_assets": f"Assets ₹{candidate.get('total_assets_inr', 0):,}; liabilities ₹{candidate.get('liabilities_inr', 0):,}.",
        "pending_cases": (
            f"{candidate.get('criminal_cases', 0)} criminal case(s) declared in 2024 affidavit."
            if candidate.get("criminal_cases", 0) > 0
            else "Zero criminal cases declared in 2024 affidavit."
        ),
        "lang": lang,
        "demo": True,
    }


def _call_gemini(prompt: str, schema: dict, timeout: int | None = None) -> dict:
    """One-shot Gemini call with structured output. Raises on failure."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GOOGLE_AI_API_KEY not configured")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.2,
        },
    }
    r = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=timeout or GEMINI_TIMEOUT_S,
    )
    r.raise_for_status()
    body = r.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def _call_gemini_grounded(prompt: str) -> tuple[str, list[dict]]:
    """Call Gemini with Google Search grounding. Returns (text, citations).

    Free tier: 500 grounded requests/day on Flash. We cache aggressively.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GOOGLE_AI_API_KEY not configured")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1},
    }
    r = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=GEMINI_TIMEOUT_S,
    )
    r.raise_for_status()
    body = r.json()
    cand = body["candidates"][0]
    text = cand["content"]["parts"][0]["text"]
    citations: list[dict] = []
    grounding = cand.get("groundingMetadata", {})
    for chunk in grounding.get("groundingChunks", []):
        web = chunk.get("web", {})
        if web.get("uri"):
            citations.append({"title": web.get("title", ""), "url": web["uri"]})
    return text, citations


# ---------------------------------------------------------------------------
# URL-spec dispatch (no OAuth — per hackathon-playbook rule #3)
# ---------------------------------------------------------------------------

def _to_calendar_format(iso_or_date: str) -> str:
    """Convert 'YYYY-MM-DD' or full ISO 8601 → 'YYYYMMDDTHHMMSSZ' (Calendar URL format)."""
    s = iso_or_date.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        # Date-only: assume 09:00 IST start of polling
        dt = datetime.strptime(s + "T09:00:00+05:30", "%Y-%m-%dT%H:%M:%S%z")
    else:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar_event_url(*, title: str, start: str, end: str | None = None,
                       details: str = "", location: str = "") -> str:
    """Build a Google Calendar 'render' URL — opens in user's logged-in tab. No OAuth."""
    start_cal = _to_calendar_format(start)
    if end:
        end_cal = _to_calendar_format(end)
    else:
        # 2-hour default slot
        from datetime import timedelta
        end_dt = datetime.strptime(start_cal, "%Y%m%dT%H%M%SZ") + timedelta(hours=2)
        end_cal = end_dt.strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_cal}/{end_cal}",
        "details": details,
        "location": location,
    }
    return "https://calendar.google.com/calendar/render?" + urllib_parse.urlencode(
        {k: v for k, v in params.items() if v}
    )


def whatsapp_share_url(text: str) -> str:
    """Open WhatsApp/WhatsApp Web with prefilled text. No auth."""
    return "https://wa.me/?text=" + urllib_parse.quote(text)


def maps_search_url(query: str) -> str:
    """Open Google Maps with a prefilled search. No API key, no auth."""
    return "https://maps.google.com/?q=" + urllib_parse.quote(query)


def eci_registration_url() -> str:
    """ECI's own voter portal — user enters EPIC ID directly there, never sent to us."""
    return "https://electoralsearch.eci.gov.in/"


# ---------------------------------------------------------------------------
# Squad helpers
# ---------------------------------------------------------------------------

def _new_squad_id() -> str:
    """12-char URL-safe random ID. Auth = knowledge of the ID."""
    return secrets.token_urlsafe(9)  # 9 bytes → 12 base64 chars


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _squad_summary_text(squad: dict, join_url: str) -> str:
    """Plaintext message used for WhatsApp share."""
    return (
        f"🗳️ Join my Voting Squad: {squad['name']}\n"
        f"{squad['constituency']}, {squad['state']} — polling on {squad['polling_date']}\n"
        f"Track who registered, researched, and voted: {join_url}\n\n"
        f"via Matdaan Mitra"
    )


# ---------------------------------------------------------------------------
# Manifesto Diff
# ---------------------------------------------------------------------------

_MANIFESTO_DIFF_SCHEMA: Final[dict] = {
    "type": "object",
    "properties": {
        "issue": {"type": "string"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string", "description": "Short label for this comparison row (max 8 words)"},
                    "party_a_position": {"type": "string", "description": "Party A's stance in 1-2 sentences"},
                    "party_a_page": {"type": "integer", "description": "Page number where this appears, or 0 if no clear page"},
                    "party_b_position": {"type": "string", "description": "Party B's stance in 1-2 sentences"},
                    "party_b_page": {"type": "integer", "description": "Page number where this appears, or 0 if no clear page"},
                },
                "required": ["point", "party_a_position", "party_b_position"],
            },
        },
    },
    "required": ["issue", "rows"],
}


def _manifesto_text(slug: str, max_pages: int = 60) -> str:
    """Render a manifesto's pages as text with [PAGE N] markers, capped to max_pages."""
    party = MANIFESTOS["parties"].get(slug)
    if not party:
        return ""
    chunks = []
    for i, page_text in enumerate(party["pages"][:max_pages], start=1):
        if page_text:
            chunks.append(f"[PAGE {i}]\n{page_text}")
    return "\n\n".join(chunks)


def _diff_prompt(slug_a: str, slug_b: str, issue_key: str, lang_name: str) -> str:
    a = MANIFESTOS["parties"][slug_a]
    b = MANIFESTOS["parties"][slug_b]
    issue_label = ISSUES.get(issue_key, issue_key)
    return (
        f"You are a neutral civic-information assistant. Compare two Indian political party "
        f"manifestos on the issue: '{issue_label}'.\n\n"
        f"Rules:\n"
        f"- Use ONLY information present in the two manifesto excerpts below.\n"
        f"- For each comparison row, extract concrete proposals (not adjectives).\n"
        f"- Give 3 to 5 rows. Each row covers ONE distinct sub-topic of '{issue_label}'.\n"
        f"- Cite page numbers from the [PAGE N] markers. If a party doesn't address the "
        f"sub-topic, say 'Not addressed in this manifesto' and set page to 0.\n"
        f"- Be balanced. Do not editorialize or rank parties.\n"
        f"- Output language: {lang_name}.\n\n"
        f"=== PARTY A: {a['name']} ({a['short']}) ===\n{_manifesto_text(slug_a)}\n\n"
        f"=== PARTY B: {b['name']} ({b['short']}) ===\n{_manifesto_text(slug_b)}\n\n"
        f"Return JSON matching the schema."
    )


def _canned_diff(slug_a: str, slug_b: str, issue_key: str, lang: str) -> dict:
    """Demo-mode diff — instant, no Gemini call. Used for stage demos."""
    a_name = MANIFESTOS["parties"].get(slug_a, {}).get("short", slug_a.upper())
    b_name = MANIFESTOS["parties"].get(slug_b, {}).get("short", slug_b.upper())
    return {
        "issue": ISSUES.get(issue_key, issue_key),
        "party_a_slug": slug_a,
        "party_b_slug": slug_b,
        "rows": [
            {"point": "Cash transfers / direct support",
             "party_a_position": f"Demo: {a_name} proposes monthly direct transfers.",
             "party_a_page": 12,
             "party_b_position": f"Demo: {b_name} proposes targeted vouchers.",
             "party_b_page": 31},
            {"point": "Legal reform",
             "party_a_position": f"Demo: {a_name} commits to fast-track courts.",
             "party_a_page": 18,
             "party_b_position": f"Demo: {b_name} commits to law-enforcement training.",
             "party_b_page": 42},
            {"point": "Workplace safety",
             "party_a_position": f"Demo: {a_name} proposes mandatory audits.",
             "party_a_page": 24,
             "party_b_position": f"Demo: {b_name} proposes safety helplines.",
             "party_b_page": 49},
        ],
        "lang": lang,
        "demo": True,
    }


# ---------------------------------------------------------------------------
# Chat assistant — Gemini intent classifier + dispatcher
# ---------------------------------------------------------------------------

_CHAT_INTENT_SCHEMA: Final[dict] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "candidate_brief",        # "tell me about X"
                "list_candidates",        # "who's running in Y"
                "list_constituencies",    # "what constituencies in Z"
                "election_info",          # "when is the election in X"
                "manifesto_diff",         # "compare X and Y on Z"
                "create_squad",           # "create a squad called X for Y"
                "help",                   # "what can you do"
                "smalltalk",              # greetings, thanks
                "unknown",
            ],
        },
        "params": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Indian state name in CAPS, e.g. TAMIL NADU"},
                "constituency": {"type": "string", "description": "Constituency name in CAPS"},
                "candidate_name": {"type": "string"},
                "party_a": {"type": "string", "description": "Party slug: bjp|inc|dmk|cpim"},
                "party_b": {"type": "string", "description": "Party slug: bjp|inc|dmk|cpim"},
                "issue": {"type": "string", "description": "Issue key: women_safety|jobs|education|healthcare|climate|farmers|youth"},
                "squad_name": {"type": "string"},
                "polling_date": {"type": "string", "description": "YYYY-MM-DD"},
                "creator_name": {"type": "string"},
            },
        },
        "reply": {
            "type": "string",
            "description": "Natural-language response. For smalltalk/help/clarification, full answer. For tool calls, a 1-line acknowledgement that will appear above the tool result.",
        },
        "needs_clarification": {
            "type": "boolean",
            "description": "True if intent matched but a required param is missing (e.g. user said 'tell me about a candidate' without naming one).",
        },
    },
    "required": ["intent", "reply", "needs_clarification"],
}


_CHAT_SYSTEM_PROMPT = """You are Matdaan Mitra, a friendly Indian election assistant. \
You help voters understand candidates, elections, manifestos, and coordinate voting plans \
with friends. Speak in the user's language (default: English). Keep replies concise (1-3 \
sentences). Be warm but neutral — never editorialize about parties or candidates.

Your job is to classify each user message into one of these intents and extract parameters:

INTENTS:
- candidate_brief — user wants details about a specific candidate (needs: candidate_name; \
  prefer state+constituency if user gave them, otherwise leave blank and the dispatcher \
  will search)
- list_candidates — user wants candidates in a constituency (needs: state, constituency)
- list_constituencies — user wants constituencies in a state (needs: state)
- election_info — user wants election dates/timeline (needs: state)
- manifesto_diff — user wants to compare two parties (needs: party_a, party_b, issue)
- create_squad — user wants to make a Voting Squad (needs: squad_name, state, \
  constituency, polling_date YYYY-MM-DD, creator_name)
- help — user asks what you can do
- smalltalk — greetings, thanks, chitchat
- unknown — anything else (ask them to rephrase)

RULES:
- Indian state and constituency names go in ALL CAPS (e.g. "TAMIL NADU", "CHENNAI CENTRAL")
- Party slugs are lowercase: bjp, inc (Congress), dmk, cpim (CPI(M))
- Issue keys: women_safety, jobs, education, healthcare, climate, farmers, youth
- For multi-turn conversations, infer context from prior messages (e.g. if user said \
  "Tamil Nadu" earlier and now asks "who's running in Chennai Central", combine them)
- If a required param is missing, set needs_clarification=true and put the question in reply
- For smalltalk and help, set needs_clarification=false and write the full answer in reply
"""


def _classify_intent(message: str, history: list[dict], lang_name: str) -> dict:
    """Run Gemini to figure out what the user wants and extract params."""
    history_block = ""
    if history:
        recent = history[-6:]
        history_block = "\nPRIOR CONVERSATION:\n" + "\n".join(
            f"{m['role']}: {m['content']}" for m in recent if m.get("content")
        ) + "\n"
    prompt = (
        _CHAT_SYSTEM_PROMPT
        + f"\n{history_block}\nUSER MESSAGE (in {lang_name}): {message}\n\n"
        f"Return JSON. The 'reply' field must be in {lang_name}."
    )
    return _call_gemini(prompt, _CHAT_INTENT_SCHEMA, timeout=15)


def _dispatch_intent(intent: str, params: dict, lang: str) -> dict:
    """Run the appropriate tool for an intent. Returns a dict with optional 'card' key."""
    p = params or {}
    if intent == "list_constituencies":
        s = CANDIDATES["states"].get(_norm_key(p.get("state", "")))
        if not s:
            return {"error": f"I don't have data for {p.get('state', 'that state')}."}
        return {"card": {"type": "constituencies", "state": p["state"],
                         "constituencies": sorted(s.keys())}}

    if intent == "list_candidates":
        s = CANDIDATES["states"].get(_norm_key(p.get("state", "")))
        if not s:
            return {"error": f"I don't have data for {p.get('state', 'that state')}."}
        cands = s.get(_norm_key(p.get("constituency", "")))
        if not cands:
            return {"error": f"I don't have data for {p.get('constituency', 'that constituency')} in {p['state']}."}
        return {"card": {"type": "candidates", "state": p["state"],
                         "constituency": p["constituency"], "candidates": cands}}

    if intent == "candidate_brief":
        name = (p.get("candidate_name") or "").strip()
        state = p.get("state") or ""
        const = p.get("constituency") or ""
        cand = _find_candidate(state, const, name) if (state and const) else None
        if not cand and name:
            cand, state, const = _fuzzy_find_candidate(name)
        if not cand:
            return {"error": f"I couldn't find a candidate named '{name}'. Try giving me their state and constituency too."}
        if DEMO_MODE:
            brief = _canned_brief(cand, lang)
        else:
            try:
                brief = _call_gemini(
                    _brief_prompt(cand, state, const, _resolve_lang(lang)),
                    _BRIEF_SCHEMA,
                )
                brief["candidate"] = cand["name"]
                brief["party"] = cand["party"]
                brief["source_url"] = CANDIDATES["source_url"]
            except (requests.Timeout, requests.ConnectionError):
                brief = {**_canned_brief(cand, lang), "fallback_reason": "gemini_timeout"}
        return {"card": {"type": "brief", "state": state, "constituency": const,
                         "candidate": cand["name"], "party": cand["party"], "data": brief}}

    if intent == "election_info":
        state = (p.get("state") or "").strip()
        if not state:
            return {"error": "Tell me which state you want election dates for."}
        if DEMO_MODE:
            info = {"state": state, "summary": f"Demo: {state} polled in 2024 LS election.",
                    "citations": [], "registration_url": eci_registration_url(), "demo": True}
        else:
            info = _get_election_info(state, _resolve_lang(lang))
        return {"card": {"type": "election", "data": info}}

    if intent == "manifesto_diff":
        a = (p.get("party_a") or "").strip().lower()
        b = (p.get("party_b") or "").strip().lower()
        issue = (p.get("issue") or "").strip()
        if a not in MANIFESTOS["parties"] or b not in MANIFESTOS["parties"] or a == b:
            return {"error": f"I have manifestos for: {', '.join(p['short'] for p in MANIFESTOS['parties'].values())}. Pick two different ones."}
        if issue not in ISSUES:
            return {"error": f"I can compare on: {', '.join(ISSUES.keys())}."}
        cache_key = f"{a}|{b}|{issue}|{lang}"
        cached = MANIFESTO_DIFF_CACHE.get(cache_key)
        if cached:
            return {"card": {"type": "diff", "data": {**cached, "cached": True}}}
        if DEMO_MODE:
            payload = _canned_diff(a, b, issue, lang)
        else:
            try:
                result = _call_gemini(
                    _diff_prompt(a, b, issue, _resolve_lang(lang)),
                    _MANIFESTO_DIFF_SCHEMA,
                    timeout=45,
                )
                pa = MANIFESTOS["parties"][a]
                pb = MANIFESTOS["parties"][b]
                payload = {**result, "party_a_slug": a, "party_b_slug": b,
                           "party_a_short": pa["short"], "party_b_short": pb["short"],
                           "party_a_source": pa["source_url"], "party_b_source": pb["source_url"],
                           "lang": lang}
            except (requests.Timeout, requests.ConnectionError):
                payload = {**_canned_diff(a, b, issue, lang), "fallback_reason": "gemini_timeout"}
        MANIFESTO_DIFF_CACHE[cache_key] = payload
        return {"card": {"type": "diff", "data": payload}}

    if intent == "create_squad":
        required = ("squad_name", "state", "constituency", "polling_date", "creator_name")
        missing = [k for k in required if not (p.get(k) or "").strip()]
        if missing:
            return {"error": f"I need: {', '.join(missing)} to create the squad."}
        squad_id = _new_squad_id()
        SQUADS[squad_id] = {
            "id": squad_id, "name": p["squad_name"], "state": p["state"],
            "constituency": p["constituency"], "polling_date": p["polling_date"],
            "members": [{"name": p["creator_name"], "registered": False, "researched": False, "voted": False}],
            "created_at": _now_iso(),
        }
        _save_squads(SQUADS)
        return {"card": {"type": "squad", "data": SQUADS[squad_id]}}

    return {}  # smalltalk / help / unknown — reply text alone is enough


# ---------------------------------------------------------------------------
# Election info (Gemini Search Grounding for live state-level dates)
# ---------------------------------------------------------------------------

_ELECTION_PROMPT_TMPL = (
    "What is the date (or date range) of the most recent or next upcoming Lok Sabha "
    "or Legislative Assembly election in {state}, India? Also state the voter registration "
    "deadline if known. Be concise (under 80 words). Answer in {lang}. If you cannot find "
    "current information, say 'No verified date available — please check eci.gov.in'."
)


def _get_election_info(state: str, lang_name: str) -> dict:
    """Cached, grounded election info for a state."""
    key = f"{_norm_key(state)}::{lang_name}"
    now = time.time()
    cached = ELECTION_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    prompt = _ELECTION_PROMPT_TMPL.format(state=state.title(), lang=lang_name)
    try:
        text, citations = _call_gemini_grounded(prompt)
    except (requests.Timeout, requests.ConnectionError):
        return {
            "state": state,
            "summary": "Live data unavailable. Please check eci.gov.in for current dates.",
            "citations": [],
            "registration_url": eci_registration_url(),
            "fallback": "gemini_timeout",
        }
    payload = {
        "state": state,
        "summary": text.strip(),
        "citations": citations,
        "registration_url": eci_registration_url(),
        "lang": lang_name,
    }
    ELECTION_CACHE[key] = (now + ELECTION_INFO_TTL_S, payload)
    return payload


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index() -> Response:
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/api/health")
def health() -> Response:
    return jsonify({
        "ok": True,
        "build_id": BUILD_ID,
        "demo_mode": DEMO_MODE,
        "candidates_loaded": CANDIDATES["total_candidates"],
        "states": len(CANDIDATES["states"]),
    })


@app.route("/api/states")
def api_states() -> Response:
    states = sorted(CANDIDATES["states"].keys())
    return jsonify({"states": states, "count": len(states)})


@app.route("/api/constituencies")
def api_constituencies() -> Response:
    state = request.args.get("state", "")
    s = CANDIDATES["states"].get(_norm_key(state))
    if not s:
        return jsonify({"error": "unknown state", "state": state}), 404
    return jsonify({"state": state, "constituencies": sorted(s.keys()), "count": len(s)})


@app.route("/api/candidates")
def api_candidates() -> Response:
    state = request.args.get("state", "")
    constituency = request.args.get("constituency", "")
    s = CANDIDATES["states"].get(_norm_key(state))
    if not s:
        return jsonify({"error": "unknown state", "state": state}), 404
    cands = s.get(_norm_key(constituency))
    if not cands:
        return jsonify({"error": "unknown constituency", "constituency": constituency}), 404
    return jsonify({
        "state": state,
        "constituency": constituency,
        "candidates": cands,
        "source": CANDIDATES["source"],
        "source_url": CANDIDATES["source_url"],
    })


@app.route("/api/brief", methods=["POST"])
def api_brief() -> Response:
    data = request.get_json(silent=True) or {}
    state = data.get("state", "")
    constituency = data.get("constituency", "")
    name = data.get("name", "")
    lang = data.get("lang", "en")

    if not (state and constituency and name):
        return jsonify({"error": "state, constituency, and name are required"}), 400

    candidate = _find_candidate(state, constituency, name)
    if not candidate:
        return jsonify({"error": "candidate not found", "state": state, "constituency": constituency, "name": name}), 404

    if DEMO_MODE:
        return jsonify(_canned_brief(candidate, lang))

    try:
        brief = _call_gemini(_brief_prompt(candidate, state, constituency, _resolve_lang(lang)), _BRIEF_SCHEMA)
    except (requests.Timeout, requests.ConnectionError):
        return jsonify({**_canned_brief(candidate, lang), "fallback_reason": "gemini_timeout"}), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "brief generation failed", "detail": str(exc)[:200]}), 503

    brief["lang"] = lang
    brief["candidate"] = candidate["name"]
    brief["party"] = candidate["party"]
    brief["source_url"] = CANDIDATES["source_url"]
    return jsonify(brief)


# ---------------------------------------------------------------------------
# Routes — My Election (state-level dates via Gemini grounding)
# ---------------------------------------------------------------------------

@app.route("/api/election-info")
def api_election_info() -> Response:
    state = request.args.get("state", "").strip()
    lang = request.args.get("lang", "en")
    if not state:
        return jsonify({"error": "state is required"}), 400

    if DEMO_MODE:
        return jsonify({
            "state": state,
            "summary": f"Demo: Lok Sabha 2024 polling in {state.title()} took place across multiple phases in April–May 2024. Next State Assembly election is on the standard 5-year cycle.",
            "citations": [{"title": "ECI", "url": "https://eci.gov.in"}],
            "registration_url": eci_registration_url(),
            "demo": True,
        })

    info = _get_election_info(state, _resolve_lang(lang))
    return jsonify(info)


# ---------------------------------------------------------------------------
# Route — Chat (the main user-facing entry; everything routes through here)
# ---------------------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    lang = data.get("lang", "en")
    history = data.get("history") or []  # [{role: "user|assistant", content: "..."}]
    if not message:
        return jsonify({"error": "message required"}), 400

    try:
        intent_data = _classify_intent(message, history, _resolve_lang(lang))
    except (requests.Timeout, requests.ConnectionError):
        return jsonify({
            "intent": "unknown", "reply": "Sorry, I couldn't reach the AI. Try again in a moment.",
            "needs_clarification": False,
        })
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "intent classification failed", "detail": str(exc)[:200]}), 503

    intent = intent_data.get("intent", "unknown")
    reply = intent_data.get("reply", "")
    needs_clarification = bool(intent_data.get("needs_clarification"))
    params = intent_data.get("params", {}) or {}

    # If the model needs more info from the user, return the question — don't run a tool.
    if needs_clarification or intent in {"smalltalk", "help", "unknown"}:
        return jsonify({"intent": intent, "reply": reply, "needs_clarification": needs_clarification,
                        "params": params})

    tool_result = _dispatch_intent(intent, params, lang)
    return jsonify({
        "intent": intent,
        "reply": reply or "",
        "params": params,
        "needs_clarification": False,
        **tool_result,
    })


@app.route("/api/suggestions")
def api_suggestions() -> Response:
    """Starter prompts for the chat UI — multilingual."""
    lang = request.args.get("lang", "en")
    by_lang = {
        "en": [
            "Compare DMK and BJP on women's safety",
            "When is the next election in Tamil Nadu?",
            "Who's running in Chennai Central?",
            "Tell me about Dayanidhi Maran",
            "Create a squad for my family",
        ],
        "hi": [
            "DMK और BJP की तुलना महिला सुरक्षा पर करें",
            "तमिलनाडु में अगला चुनाव कब है?",
            "चेन्नई सेंट्रल में कौन खड़ा है?",
            "दयानिधि मारन के बारे में बताइए",
            "मेरे परिवार के लिए स्क्वाड बनाएं",
        ],
    }
    return jsonify({"suggestions": by_lang.get(lang, by_lang["en"])})


# ---------------------------------------------------------------------------
# Routes — Manifesto Diff (kept for direct API use; chat dispatches here too)
# ---------------------------------------------------------------------------

@app.route("/api/parties")
def api_parties() -> Response:
    parties = [
        {"slug": slug, "name": p["name"], "short": p["short"], "color": p["color"], "pages": p["page_count"]}
        for slug, p in MANIFESTOS["parties"].items()
    ]
    return jsonify({
        "parties": parties,
        "issues": [{"key": k, "label": v} for k, v in ISSUES.items()],
        "source": MANIFESTOS.get("source"),
        "source_url": MANIFESTOS.get("source_url"),
    })


@app.route("/api/manifesto-diff", methods=["POST"])
def api_manifesto_diff() -> Response:
    data = request.get_json(silent=True) or {}
    slug_a = (data.get("a") or "").strip().lower()
    slug_b = (data.get("b") or "").strip().lower()
    issue = (data.get("issue") or "").strip()
    lang = data.get("lang", "en")

    if not (slug_a and slug_b and issue):
        return jsonify({"error": "a, b, and issue are required"}), 400
    if slug_a == slug_b:
        return jsonify({"error": "a and b must be different parties"}), 400
    if slug_a not in MANIFESTOS["parties"] or slug_b not in MANIFESTOS["parties"]:
        return jsonify({"error": "unknown party slug", "have": list(MANIFESTOS["parties"].keys())}), 404
    if issue not in ISSUES:
        return jsonify({"error": "unknown issue", "have": list(ISSUES.keys())}), 400

    cache_key = f"{slug_a}|{slug_b}|{issue}|{lang}"
    cached = MANIFESTO_DIFF_CACHE.get(cache_key)
    if cached:
        return jsonify({**cached, "cached": True})

    if DEMO_MODE:
        payload = _canned_diff(slug_a, slug_b, issue, lang)
        MANIFESTO_DIFF_CACHE[cache_key] = payload
        return jsonify(payload)

    try:
        result = _call_gemini(
            _diff_prompt(slug_a, slug_b, issue, _resolve_lang(lang)),
            _MANIFESTO_DIFF_SCHEMA,
            timeout=45,  # heavy prompt: ~50k tokens of manifesto text
        )
    except (requests.Timeout, requests.ConnectionError):
        payload = _canned_diff(slug_a, slug_b, issue, lang)
        return jsonify({**payload, "fallback_reason": "gemini_timeout"})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "diff generation failed", "detail": str(exc)[:200]}), 503

    a = MANIFESTOS["parties"][slug_a]
    b = MANIFESTOS["parties"][slug_b]
    payload = {
        **result,
        "party_a_slug": slug_a, "party_b_slug": slug_b,
        "party_a_name": a["name"], "party_b_name": b["name"],
        "party_a_short": a["short"], "party_b_short": b["short"],
        "party_a_source": a["source_url"], "party_b_source": b["source_url"],
        "lang": lang,
    }
    MANIFESTO_DIFF_CACHE[cache_key] = payload
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Routes — Voting Squad
# ---------------------------------------------------------------------------

@app.route("/api/squad", methods=["POST"])
def api_squad_create() -> Response:
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    state = (data.get("state") or "").strip()
    constituency = (data.get("constituency") or "").strip()
    polling_date = (data.get("polling_date") or "").strip()  # YYYY-MM-DD
    creator = (data.get("creator") or "").strip()

    if not all([name, state, constituency, polling_date, creator]):
        return jsonify({"error": "name, state, constituency, polling_date, creator required"}), 400

    squad_id = _new_squad_id()
    SQUADS[squad_id] = {
        "id": squad_id,
        "name": name,
        "state": state,
        "constituency": constituency,
        "polling_date": polling_date,
        "members": [
            {"name": creator, "registered": False, "researched": False, "voted": False},
        ],
        "created_at": _now_iso(),
    }
    _save_squads(SQUADS)

    join_url = request.host_url.rstrip("/") + f"/squad/{squad_id}"
    return jsonify({
        "squad_id": squad_id,
        "join_url": join_url,
        "whatsapp_share_url": whatsapp_share_url(_squad_summary_text(SQUADS[squad_id], join_url)),
    }), 201


@app.route("/api/squad/<squad_id>")
def api_squad_get(squad_id: str) -> Response:
    squad = SQUADS.get(squad_id)
    if not squad:
        return jsonify({"error": "squad not found"}), 404
    join_url = request.host_url.rstrip("/") + f"/squad/{squad_id}"
    return jsonify({
        **squad,
        "join_url": join_url,
        "whatsapp_share_url": whatsapp_share_url(_squad_summary_text(squad, join_url)),
        "calendar_url": calendar_event_url(
            title=f"Vote together — {squad['name']}",
            start=squad["polling_date"],
            details=f"Polling day for {squad['constituency']}, {squad['state']}.\n\nTrack progress: {join_url}",
            location=f"{squad['constituency']}, {squad['state']}, India",
        ),
        "maps_url": maps_search_url(f"polling station {squad['constituency']} {squad['state']}"),
    })


@app.route("/squad/<squad_id>")
def squad_page(squad_id: str) -> Response:
    squad = SQUADS.get(squad_id)
    if not squad:
        return render_template("squad_not_found.html", squad_id=squad_id), 404
    return render_template("squad.html", squad=squad)


@app.route("/api/squad/<squad_id>/join", methods=["POST"])
def api_squad_join(squad_id: str) -> Response:
    squad = SQUADS.get(squad_id)
    if not squad:
        return jsonify({"error": "squad not found"}), 404
    data = request.get_json(silent=True) or {}
    member_name = (data.get("name") or "").strip()
    if not member_name:
        return jsonify({"error": "name required"}), 400
    if any(m["name"].lower() == member_name.lower() for m in squad["members"]):
        return jsonify({"error": "member already in squad", "name": member_name}), 409
    squad["members"].append({"name": member_name, "registered": False, "researched": False, "voted": False})
    _save_squads(SQUADS)
    return jsonify({"ok": True, "members": squad["members"]})


@app.route("/api/squad/<squad_id>/checkin", methods=["POST"])
def api_squad_checkin(squad_id: str) -> Response:
    squad = SQUADS.get(squad_id)
    if not squad:
        return jsonify({"error": "squad not found"}), 404
    data = request.get_json(silent=True) or {}
    member_name = (data.get("name") or "").strip()
    flags = {k: bool(data.get(k)) for k in ("registered", "researched", "voted") if k in data}
    if not member_name or not flags:
        return jsonify({"error": "name and at least one of registered/researched/voted required"}), 400
    for m in squad["members"]:
        if m["name"].lower() == member_name.lower():
            m.update(flags)
            _save_squads(SQUADS)
            return jsonify({"ok": True, "member": m})
    return jsonify({"error": "member not found", "name": member_name}), 404


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@app.after_request
def gzip_response(response: Response) -> Response:
    """Compress JSON/HTML responses when the client accepts gzip."""
    if response.direct_passthrough or response.status_code < 200 or response.status_code >= 300:
        return response
    if response.headers.get("Content-Encoding"):
        return response
    if "gzip" not in (request.headers.get("Accept-Encoding") or ""):
        return response
    if response.content_length is not None and response.content_length < 500:
        return response
    data = gzip.compress(response.get_data(), compresslevel=6)
    response.set_data(data)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(data))
    response.headers["Vary"] = "Accept-Encoding"
    return response


# ---------------------------------------------------------------------------
# Local dev entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
