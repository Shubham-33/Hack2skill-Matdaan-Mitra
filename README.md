# मतदान मित्र · Matdaan Mitra

[![CI](https://github.com/Shubham-33/Hack2skill-Matdaan-Mitra/actions/workflows/ci.yml/badge.svg)](https://github.com/Shubham-33/Hack2skill-Matdaan-Mitra/actions/workflows/ci.yml)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![python](https://img.shields.io/badge/python-3.10-blue)
![license](https://img.shields.io/badge/license-MIT-green)

**Your voting buddy — from registration to booth.**

A multilingual, accessible election companion for Indian voters. Built for **Hack2skill Solution Challenge 2026** under the *Team Collaboration Tool* problem statement: helping users understand the election process, timelines, and steps in an interactive and easy-to-follow way.

---

## What it does

Four tiles, one page, no login:

1. **🪪 Candidate Snapshot** — Pick any 2024 Lok Sabha constituency from 23 states. Get a Gemini-generated 3-bullet brief in your language with sourced facts (background, disclosed assets, pending cases as filed in the affidavit). 2,810 candidates indexed.

2. **🗳️ My Election** — Pick your state. Gemini Search Grounding fetches live election dates and registration deadlines, with citations to news/Wikipedia/ECI. Deeplinks to the official ECI portal so your EPIC ID never leaves your browser.

3. **📑 Manifesto Diff** — Pick two parties + an issue. Gemini reads both manifestos (we ship 4 — BJP, INC, DMK, CPI(M)) and produces a side-by-side comparison table with **page citations** to the source PDFs.

4. **👥 Voting Squad** — Create a squad → share a link via WhatsApp → friends/family check off "Registered / Researched / Voted." Group calendar invite via Google Calendar URL spec. **No OAuth.**

Cross-cutting: **5 native languages** (English, Hindi, Tamil, Bengali, Marathi) + Gemini auto-translate fallback for any of the other 17 official Indian languages. **Voice input** (Web Speech API) and **read-aloud** (`window.speechSynthesis`) on every text block.

---

## Live demo

Coming soon — deployable to Cloud Run with `web/deploy.sh` (see Deploy section).

```bash
# Local
.venv/bin/python web/app.py
open http://localhost:5050
```

90-second demo flow:

| Time | Action |
|------|--------|
| 0–5s | Open URL, language=Hindi pre-selected |
| 5–20s | **Manifesto Diff** loads sample (DMK vs BJP, women's safety) — table of 5 substantive points with real page citations |
| 20–35s | **Candidate Snapshot** for Chennai Central, brief in Hindi, source link to OpenCity affidavit data |
| 35–55s | **Voting Squad** — fill form → create → "Add to Calendar" opens prefilled Google Calendar tab → "WhatsApp" opens share dialog |
| 55–75s | **My Election** — pick Tamil Nadu → live dates from Gemini grounding with Wikipedia + ECI + news citations |
| 75–90s | Tap mic 🎤 → speak "Tamil Nadu" → election info loads → tap 🔊 → response read aloud in Hindi |

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
  app.py                # ~700 LOC, all routes + helpers
  templates/            # index.html + squad.html + squad_not_found.html
  static/               # app.js + app.css (cache-busted via build_id)
  data/                 # shipped read-only data (candidates, manifestos)
  tests/                # 51 tests, ~96% coverage
  deploy.sh             # Cloud Run + Secret Manager + IAM in one shot
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
| **Testing** | **51/51 pytest tests passing, 95.78% coverage**, gate enforced via `pyproject.toml` `fail_under=85`. Mocks all external HTTP. |
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

**Hack2skill Solution Challenge 2026** · 3-day build · Python 3.10 · Flask 3 · Gemini 2.5 Flash · 51 tests · 95.78% coverage · zero credit cards.
