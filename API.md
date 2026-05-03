# API Reference

All endpoints are served by `web/app.py` on Cloud Run.
Base URL: `https://matdaan-mitra-amigady5dq-el.a.run.app`

## Authentication
None. The app is anonymous-first by design — privacy through not collecting.

## Rate limiting
`/api/chat` is limited to **30 requests per 60 seconds per IP** (sliding window). Exceeding returns 429 with `{"intent": "rate_limited"}`.

## Security headers (every response)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), camera=(), usb=(), microphone=(self), …`
- `Content-Security-Policy: …` (Google domains allowlisted)

---

## `GET /api/health`
Liveness probe. Used by Cloud Run + smoke tests.

**Response:**
```json
{
  "ok": true,
  "build_id": "1777819374",
  "demo_mode": false,
  "candidates_loaded": 2810,
  "states": 23
}
```

---

## `POST /api/chat`
**The main entry point.** Classifies user intent + dispatches to a tool.

**Request body:**
```json
{
  "message": "Compare DMK and BJP on women's safety",
  "lang": "en",
  "history": [
    {"role": "user", "content": "previous message"},
    {"role": "assistant", "content": "previous reply"}
  ]
}
```
- `message` — required, ≤2000 chars
- `lang` — one of `en, hi, ta, bn, mr` (default `en`); other Indian language codes accepted with Gemini fallback
- `history` — optional, ≤50 turns

**Response:**
```json
{
  "intent": "manifesto_diff",
  "reply": "Comparing the two manifestos for you.",
  "needs_clarification": false,
  "params": { "party_a": "dmk", "party_b": "bjp", "issue": "women_safety" },
  "card": {
    "type": "diff",
    "data": {
      "issue": "Women's safety",
      "rows": [
        { "point": "Reservation in Parliament",
          "party_a_position": "DMK commits to immediate 33% reservation",
          "party_a_page": 20,
          "party_b_position": "BJP will systematically implement Nari Shakti Vandan Adhiniyam",
          "party_b_page": 9 }
      ],
      "party_a_short": "DMK", "party_b_short": "BJP",
      "party_a_source": "https://www.dmk.in/...",
      "party_b_source": "https://www.bjp.org/manifesto"
    }
  }
}
```

**Possible intents:**
| Intent | When | Card type |
|---|---|---|
| `candidate_brief` | "Tell me about X" | `brief` |
| `list_candidates` | "Who's running in Y" | `candidates` |
| `list_constituencies` | "What constituencies in Z" | `constituencies` |
| `election_info` | "When is the election in X" | `election` |
| `manifesto_diff` | "Compare X and Y on Z" | `diff` |
| `create_squad` | "Make a squad for ..." | `squad` |
| `explain_process` | "How do I register / vote / find my booth" | (text only — full instructional reply in `reply` field) |
| `help` | "What can you do" | (text only) |
| `smalltalk` | Greetings, thanks | (text only) |
| `unknown` | Anything else | (text only — clarifying question) |

**Errors:** 400 (bad input · message too long · invalid history), 429 (rate limit), 503 (Gemini classifier failed).

---

## `GET /api/states`
List all 23 Indian states with candidate data.

**Response:**
```json
{ "states": ["TAMIL NADU", "MAHARASHTRA", ...], "count": 23 }
```

---

## `GET /api/constituencies?state=...`
List constituencies in a state.

**Response (200):** `{ "state": "TAMIL NADU", "constituencies": [...], "count": 39 }`
**404:** Unknown state.

---

## `GET /api/candidates?state=...&constituency=...`
List candidates in a (state, constituency) pair.

**Response (200):** `{ "state": "...", "constituency": "...", "candidates": [...], "source": "OpenCity ...", "source_url": "..." }`
**404:** Unknown state or constituency.

---

## `POST /api/brief`
Direct candidate brief endpoint (chat dispatches here too).

**Body:** `{ "state", "constituency", "name", "lang" }`
**Response:** `{ "background", "disclosed_assets", "pending_cases", "candidate", "party", "source_url", "lang" }`
**Falls back** to a canned brief on Gemini timeout (HTTP 200 with `fallback_reason: "gemini_timeout"`).

---

## `GET /api/election-info?state=...&lang=en`
Live election dates for a state via **Gemini Search Grounding** (cached 1 hour per state-lang).

**Response:** `{ "state", "summary", "citations": [{title, url}, ...], "registration_url" }`

---

## `GET /api/parties`
List parties with manifestos shipped + supported issue keys.

**Response:**
```json
{
  "parties": [{ "slug": "bjp", "name": "...", "short": "BJP", "color": "#FF9933", "pages": 76 }, ...],
  "issues": [{ "key": "women_safety", "label": "Women's safety and gender equality" }, ...],
  "source": "OpenCity ...", "source_url": "..."
}
```

---

## `POST /api/manifesto-diff`
Direct manifesto diff (chat dispatches here too).

**Body:** `{ "a": "dmk", "b": "bjp", "issue": "women_safety", "lang": "en" }`
**Response:** `{ "issue", "rows": [...], "party_a_*", "party_b_*", "lang", "cached"? }`
**400:** Missing fields or same party twice.
**404:** Unknown party slug.

---

## Voting Squad (4 endpoints)

### `POST /api/squad`
Create. Body: `{ name, creator, state, constituency, polling_date }` — all required.
Response 201: `{ squad_id, join_url, whatsapp_share_url }`

### `GET /api/squad/<squad_id>`
Fetch squad state + every deeplink (calendar, whatsapp, maps).

### `POST /api/squad/<squad_id>/join`
Add a member. Body: `{ name }`. Returns the updated members list. **409** if name already exists.

### `POST /api/squad/<squad_id>/checkin`
Update one member's checkboxes. Body: `{ name, registered?, researched?, voted? }` — at least one boolean required.

### `GET /squad/<squad_id>` (HTML, not JSON)
The shareable join page. **404** if squad doesn't exist (renders a friendly not-found page).

---

## `GET /api/suggestions?lang=en`
Starter prompts for the chat UI in the requested language.

**Response:** `{ "suggestions": ["How do I register to vote?", ...] }` — currently 6 prompts in `en` and `hi`; other langs fall back to `en`.

---

## Internal status codes
- 200 OK — success
- 201 Created — squad created
- 400 Bad Request — input validation failed
- 404 Not Found — unknown state/constituency/squad/party
- 409 Conflict — duplicate squad member
- 429 Too Many Requests — rate limited (chat) or Gemini quota exhausted
- 503 Service Unavailable — Gemini classifier or generation hard-failed (after fallback exhausted)
