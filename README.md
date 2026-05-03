# मतदान मित्र · Matdaan Mitra

[![CI](https://github.com/Shubham-33/Hack2skill-Matdaan-Mitra/actions/workflows/ci.yml/badge.svg)](https://github.com/Shubham-33/Hack2skill-Matdaan-Mitra/actions/workflows/ci.yml)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![python](https://img.shields.io/badge/python-3.10-blue)
![license](https://img.shields.io/badge/license-MIT-green)

**Your voting buddy — from registration to booth.**

A multilingual, accessible election companion for Indian voters. Built for **Hack2skill Solution Challenge 2026** under the *Team Collaboration Tool* problem statement: helping users understand the election process, timelines, and steps in an interactive and easy-to-follow way.

---

## What it does

A **chat assistant** — type or speak any election question, get a useful answer with sources.

### Sample conversations

| You ask | The assistant does |
|---|---|
| *"Who's running in Chennai Central?"* | Lists 31 candidates with party + winner indicators |
| *"Tell me about Dayanidhi Maran"* | Gemini-generated 3-bullet brief over OpenCity 2024 affidavit data — background · disclosed assets · pending cases as filed |
| *"When is the next election in Tamil Nadu?"* | Live dates via Gemini Search Grounding, with citations to ECI / Wikipedia / news |
| *"Compare DMK and BJP on women's safety"* | Side-by-side table reading both manifesto PDFs (BJP · INC · DMK · CPI(M)), with page-number citations |
| *"Create a squad for my family in Chennai Central, polling 15 May 2026"* | Returns a sharable join link + Google Calendar deeplink + WhatsApp share button |
| *"दयानिधि मारन के बारे में बताइए"* | Same brief, in Devanagari — fuzzy-matches the Hindi name to the Latin record |

### How it works
1. Single chat input + voice mic 🎤 (Web Speech API)
2. Gemini intent classifier reads your message + history → picks one of 9 intents → extracts params
3. Backend dispatches to the right tool (candidate brief, election lookup, manifesto diff, squad create, etc.)
4. Response renders inline as a structured card; tap 🔊 to read it aloud
5. **5 native Indian languages** (EN/HI/TA/BN/MR) + Gemini fallback for 17 more

---

## Live demo

🔗 **https://matdaan-mitra-amigady5dq-el.a.run.app** (running on Cloud Run, asia-south1)

```bash
# Local
.venv/bin/python web/app.py
open http://localhost:5050
```

90-second demo flow:

| Time | Action |
|------|--------|
| 0–10s | Open URL, language=Hindi pre-selected via `?lang=hi`. Greeting + suggested prompts |
| 10–25s | Tap *"Compare DMK and BJP on women's safety"* → side-by-side table, page citations |
| 25–40s | Type *"who's running in chennai central"* → 31 candidate chips (auto-inferred Tamil Nadu) |
| 40–55s | Tap one → 3-bullet Hindi brief, source link to OpenCity affidavit |
| 55–70s | *"create a squad called Family for chennai central polling 15 May 2026, my name is Shubham"* → squad card with WhatsApp + Calendar buttons |
| 70–90s | Tap mic 🎤 → speak "Tamil Nadu" → election dates load → tap 🔊 → response read aloud in Hindi |

---

## Architecture

Three-layer architecture per `CLAUDE.MD`:

```
directives/             # SOPs in Markdown (the "what")
  build_matdaan_mitra.md
  sync_candidates.md
  generate_brief.md
  manifesto_diff.md
  squad_calendar_share.md
execution/              # Deterministic Python (the "how")
  sync_candidates.py    # OpenCity CSV → web/data/candidates.json
  sync_manifestos.py    # PDFs → text-with-page-markers JSON
web/                    # Flask app
  app.py                # ~1100 LOC, all routes + helpers
  templates/            # index.html (chat UI) + squad.html (join page)
  static/               # app.js + app.css (cache-busted via build_id)
  data/                 # shipped read-only data (candidates, manifestos)
  tests/                # 96 tests, 100% coverage gate
  deploy.sh             # Cloud Run + Secret Manager + IAM in one shot
```

### How a chat message flows
```
User types/speaks
   ↓
POST /api/chat { message, lang, history }
   ↓
_classify_intent() → Gemini Flash → { intent, params, reply }
                     (auto-fallback to Flash-Lite if 429)
   ↓
_dispatch_intent(intent, params) → calls the right tool:
   • candidate_brief  → Gemini brief over OpenCity affidavit row
   • election_info    → Gemini Search Grounding for state dates
   • manifesto_diff   → Gemini reads 2 manifestos → table with page cites
   • create_squad     → JSON file + Calendar URL + WhatsApp URL
   • list_*           → direct lookup, no LLM
   ↓
Frontend renders text bubble or structured card
```

The agent (Claude) orchestrates: reads directives, calls execution scripts, fixes errors, updates directives with learnings. LLMs are probabilistic; business logic stays deterministic. See `CLAUDE.MD` for the full pattern.

---

## Tech stack — 100% free tier

| Layer | Choice | Why |
|---|---|---|
| Web server | **Flask + Tailwind CDN** (no Node, no build) | Single `app.py`, ~10s deploy via Cloud Run buildpacks |
| LLM | **Gemini 2.5 Flash** via REST | 250 RPD free + 250k TPM |
| Live web data | **Gemini Search Grounding** | 500 grounded RPD free on Flash |
| Embeddings (future) | **`text-embedding-004`** | Free |
| Hosting | **Firebase Hosting** or **Cloud Run** (this build uses Run) | Generous free tier in `asia-south1` |
| Secrets | **Google Cloud Secret Manager** | Free for low volume |
| Database | **JSON files + in-memory dict** | Hackathon-appropriate; squads persist to disk |
| Calendar | **Google Calendar URL spec** (no OAuth) | `https://calendar.google.com/calendar/render?action=TEMPLATE&...` |
| Sharing | **`wa.me`** WhatsApp deeplink | No app/auth |
| Maps | **`maps.google.com/?q=...`** deeplink | No API key required |
| Voice in | **Web Speech API** (`webkitSpeechRecognition`) | Browser-native, free |
| Voice out | **Web Speech API** (`speechSynthesis`) | Browser-native, free |
| PDF parsing | **pypdf** | Pure Python, no system deps |

**No credit card required.** No OAuth flows. No SDK installs (Gemini hit via plain `requests`).

---

## Data sources (all Public Domain, sourced from ECI)

- **Candidate affidavits**: [OpenCity Parliamentary Elections 2024 Affidavits](https://data.opencity.in/dataset/parliamentary-elections-2024-affidavits) — 2,810 candidates across 23 states. License: Other (Public Domain). Original source: Election Commission of India.
- **Party manifestos**: [OpenCity Parliamentary Elections 2024 Manifestos](https://data.opencity.in/dataset/parliamentary-elections-2024-manifestos) — BJP, INC, DMK, CPI(M) for the demo. License: Other (Public Domain).
- **Live election dates**: Gemini Search Grounding, citing Wikipedia, ECI, The Hindu, India Today, Deccan Herald, etc.

We deliberately do **not** redistribute MyNeta data because their Terms of Use prohibit it. We use the original ECI source via OpenCity's Public Domain rebundle. Every fact in the UI links back to the source.

---

## Privacy & security

- **No login.** No accounts. No tracking.
- **EPIC ID never leaves your browser.** Voter-registration check deeplinks to `electoralsearch.eci.gov.in`.
- **Squad ID = auth.** 12-char URL-safe random token. Anyone with the link can join the squad. No sensitive data in squads.
- **API key in Secret Manager** when deployed; in `.env` (gitignored) locally.
- **DPDP Act 2023** considered: we collect nothing personally identifiable.

---

## Hack2skill judging mapping

| Parameter | Evidence |
|---|---|
| **Code Quality** | 3-layer architecture (directives / execution / app), type hints, section banners, ruff config, README, one-command setup, 700 LOC well-organized |
| **Security** | No PII storage, no OAuth, Secret Manager for keys, `.gcloudignore` excludes `.env`, gzip middleware, `Cache-Control` headers, all routes input-validated |
| **Efficiency** | Free-tier-only stack, gzip compression, asset caching with `build_id` query string, in-memory caches for election dates (1h TTL) and manifesto diffs (forever), `--min-instances=1 --cpu-boost` on Cloud Run |
| **Testing** | **96/96 pytest tests passing, 100.00% coverage**, gate enforced via `pyproject.toml` `fail_under=100`. ruff-clean, GitHub Actions CI on every push. Mocks all external HTTP. |
| **Accessibility** | 5 native Indian languages + Gemini fallback for 17 more, Web Speech TTS read-aloud on every text block, mic input for queries, keyboard ⌘/Ctrl+Enter shortcut, ARIA labels everywhere, focus rings, skip-to-content link, `role="status"` live regions, semantic HTML |
| **Problem Alignment** | Direct: explains process (Candidate Snapshot, My Election), shows timelines (My Election dates), shows steps (Voting Squad checkboxes). Adds the *team collaboration* dimension via Squad. |
| **Google Services** | Gemini 2.5 Flash · Gemini Search Grounding · Google Calendar (URL spec) · Google Maps (deeplink) · Web Speech API · Cloud Run · Secret Manager · Firebase Hosting (alt) — **8 Google services** |

---

## Setup

```bash
# 1) clone, enter the repo
cd "Hack2skill - Challange 2v2"

# 2) create .env from template, paste your Gemini API key
cp .env.example .env
# edit .env, set GOOGLE_AI_API_KEY=AIzaSy...

# 3) install Python 3.10+ deps
python3.10 -m venv .venv
.venv/bin/pip install -r web/requirements.txt -r web/requirements-dev.txt

# 4) sync open-data sources (one-shot)
.venv/bin/python execution/sync_candidates.py
.venv/bin/python execution/sync_manifestos.py

# 5) run locally
.venv/bin/python web/app.py
# → http://localhost:5050

# 6) run tests
cd web && ../.venv/bin/python -m pytest -q
```

---

## Deploy to Cloud Run

```bash
# In Cloud Shell (gcloud preinstalled, pre-authed)
git clone https://github.com/<you>/<repo>.git ~/matdaan-mitra
cd ~/matdaan-mitra/web
chmod +x deploy.sh
./deploy.sh <PROJECT_ID> <GEMINI_API_KEY>
```

`deploy.sh` enables required APIs, stores the key in Secret Manager, grants the runtime service account access, and deploys via buildpacks (no Dockerfile needed). Region default: `asia-south1` (Mumbai). Min instances: 1 (avoids cold starts during demo).

---

## What this is NOT

- ❌ Live election results · exit polls · winner predictions
- ❌ News feed · social feed · debate transcripts
- ❌ Election betting (illegal in India)
- ❌ A replacement for `eci.gov.in` — every factual claim links back to the source

---

## License

Code: MIT. Data: Public Domain (per OpenCity's licensing of the underlying ECI sources).

---

## Built with

**Hack2skill Solution Challenge 2026** · 3-day build · Python 3.10 · Flask 3 · Gemini 2.5 Flash · **96 tests · 100% coverage** · zero credit cards.
