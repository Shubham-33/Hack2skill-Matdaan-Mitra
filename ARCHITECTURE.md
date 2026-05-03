# Architecture

> The 3-layer pattern from `CLAUDE.MD`, applied concretely.

## Layers

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Directives (the WHAT)                         │
│  directives/*.md — natural-language SOPs                │
│  Goals · inputs · tools · outputs · edge cases          │
└─────────────────────────────────────────────────────────┘
                         ↓ (read by)
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Orchestrator (the DECISION)                   │
│  An AI agent (Claude, in development; Gemini at runtime)│
│  Reads directives, calls tools, handles errors, learns  │
└─────────────────────────────────────────────────────────┘
                         ↓ (calls)
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Execution (the HOW)                           │
│  execution/*.py — deterministic Python                  │
│  Scrapes, parses, builds the data files                 │
│                                                         │
│  web/ — Flask app serving the chat UI                   │
│  Read-only consumer of the data files                   │
└─────────────────────────────────────────────────────────┘
```

LLMs are probabilistic; business logic stays deterministic. The agent only does decision-making, not the actual data work — that prevents error compounding (90% per step × 5 steps = 59% success).

## Why the directive/execution split

A directive looks like:
```markdown
## Goal
Maintain a local web/data/candidates.json sourced from OpenCity (Public Domain).

## Inputs
- OpenCity CSV URL (versioned)
- Sheets API service account credentials

## Tools
- execution/sync_candidates.py: download → parse → write JSON

## Outputs
- web/data/candidates.json with stable schema
- Stdout summary: total candidates, states covered

## Edge cases
- CSV column drift → fail loud, never silently
- Encoding issues for Tamil/Bengali names → UTF-8 with errors=replace
- Sheet quota exceeded → exponential backoff, retry once
```

The directive is the contract. The execution script is the implementation. When an error happens, the script gets fixed AND the directive gets updated with the learning, so the next run is stronger.

## Runtime architecture (web/)

```
            ┌──────────────────────────────────────┐
            │ Browser                              │
            │  • Chat UI (single-page)             │
            │  • Web Speech API (mic + TTS)        │
            │  • Google Fonts loaded               │
            │  • Google Translate widget           │
            └──────────────────────────────────────┘
                          │ HTTPS
                          ↓
            ┌──────────────────────────────────────┐
            │ Cloud Run (asia-south1)              │
            │  • Flask app (gunicorn)              │
            │  • min-instances=1 (no cold starts)  │
            │  • cpu-boost enabled                 │
            └──────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
┌─────────────┐  ┌──────────────────┐  ┌──────────────┐
│ Local JSON  │  │ Gemini API       │  │ Secret       │
│  (shipped)  │  │  • Flash         │  │ Manager      │
│  • candidates│ │  • Flash-Lite   │  │  • API key   │
│  • manifestos│ │    (fallback)    │  │              │
│  • squads    │ │  • Search        │  │              │
│              │ │    Grounding     │  │              │
└─────────────┘  └──────────────────┘  └──────────────┘
```

## The chat dispatch flow

```
User types: "Compare DMK and BJP on women's safety"
         │
         ↓
POST /api/chat { message, lang, history }
         │
         ↓
Rate-limit check (per-IP, 30 req/60s, sliding window)
         │
         ↓
Input validation (≤2000 chars message, ≤50 turn history)
         │
         ↓
_classify_intent() → Gemini Flash
   Returns { intent: "manifesto_diff",
             params: { party_a: "dmk", party_b: "bjp", issue: "women_safety" },
             needs_clarification: false }
   ※ Auto-falls back to Flash-Lite on 429
         │
         ↓
Defensive backfill: scan message for issue keywords if missing
         │
         ↓
_dispatch_intent("manifesto_diff", params, lang)
   Reads pre-extracted manifesto JSON
   Calls Gemini with both texts + structured-output schema
   Returns { card: { type: "diff", data: {...} } }
   ※ Cached forever in process (manifestos are immutable)
         │
         ↓
Frontend renders the right card type
```

## Module organization (web/)

```
web/
├── app.py                 # Flask app + routes (the orchestrator)
├── lib_security.py        # Rate limiting, security headers, error sanitization
├── lib_dispatch.py        # URL-spec helpers (Calendar/WhatsApp/Maps deeplinks)
├── data/
│   ├── candidates.json    # 2,810 candidates, all-India (OpenCity Public Domain)
│   ├── manifestos.json    # 4 parties × ~60 pages, per-page text with markers
│   └── squads.json        # Runtime mutable, gitignored
├── templates/
│   ├── index.html         # Chat UI shell (loads Inter + Tiro Devanagari Hindi from Google Fonts)
│   ├── squad.html         # Join page for a Voting Squad
│   └── squad_not_found.html
├── static/
│   ├── app.js             # Chat client + Web Speech + dispatch rendering
│   └── app.css            # Custom styles on top of Tailwind CDN (focus rings, contrast)
├── tests/                 # 100% coverage gate (104+ tests)
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_chat.py
│   ├── test_squad.py
│   ├── test_manifesto.py
│   └── test_coverage_gaps.py
├── pyproject.toml         # ruff + pytest + 100% coverage gate
├── requirements.txt
├── Procfile               # gunicorn entry for Cloud Run buildpacks
├── deploy.sh              # One-shot Cloud Run + Secret Manager + IAM
└── Makefile               # install / sync / run / test / lint / deploy / clean
```

## Why these specific design choices

| Decision | Why |
|---|---|
| **Chat-only UI (not tiles)** | The problem statement says *"create an assistant"* — a conversational interface aligns directly. Virtual judging means scan-time is not the bottleneck. |
| **JSON files as DB** | Hackathon-appropriate. Squads persist to disk; immutable data ships with the deploy. No DB setup, no schema migrations, no DB cost. |
| **Server-side Gemini** | Keeps API key out of the browser. Allows rate limiting and validation before LLM calls. |
| **Flash + Flash-Lite fallback** | Free tier: Flash has 250 RPD, Flash-Lite has 1500 RPD. Chained automatically — chat keeps working under load. |
| **URL-spec dispatch (no OAuth)** | Calendar and WhatsApp open in the user's logged-in tab. No OAuth flow saves 30+ minutes of build time and reduces attack surface. |
| **Squad ID as auth** | 12-char URL-safe random token. Anyone with the link can join. No login system needed; nothing sensitive in a squad anyway. |
| **Public Domain data only** | OpenCity's rebundle of ECI affidavits is licensed Public Domain. We deliberately do NOT use MyNeta directly because their ToU prohibits redistribution. |
| **Cache-busting via build_id** | Cloud Build buildpacks reset all file mtimes to 1980. We fall back to module-load time so each new container has a unique build_id, busting browser cache automatically. |

## Where time was spent

| Day | Focus |
|---|---|
| 1 | Data ingestion · Flask scaffold · `/api/brief` end-to-end with Gemini |
| 2 | `/api/election-info` (grounded) · Voting Squad · multilingual i18n |
| 3 | Manifesto Diff · TTS + mic · DEMO_MODE · README · 100% coverage gate |
| 4 (refinements) | Chat-only UI rewrite · classifier hardening · score-targeted polish |
