# Build Matdaan Mitra — Master Directive

> Indian election companion app for Hack2skill Solution Challenge 2026. Built per the hackathon-playbook skill (Flask + Cloud Run + URL-spec dispatch + Sheets-as-DB).

## Goal
Ship a deployed, multilingual, accessible Indian election assistant covering all states, with 4 features (My Election, Candidate Snapshot, Manifesto Diff, Voting Squad), in 3 days, on free tier only.

## Inputs
- `GOOGLE_AI_API_KEY` from `.env` (Gemini 2.5 Flash + Search Grounding)
- A Google Cloud project with Cloud Run + Secret Manager + Sheets API enabled
- A Google Sheet `MatdaanMitra_DB` with two tabs: `Candidates` (synced from GitHub mirror) and `Squads` (squad state)
- Service-account JSON for Sheets access (mounted as `GOOGLE_APPLICATION_CREDENTIALS`)
- 4 manifesto PDFs in `web/data/manifestos/` for the demo states (Tamil Nadu, West Bengal, Kerala, Assam)

## Tools / scripts
1. `execution/sync_candidates.py` — weekly cron, GitHub mirror → Sheet
2. `web/app.py` — Flask app, all endpoints
3. `web/deploy.sh` — Cloud Run deploy with Secret Manager + IAM in one shot
4. Other directives drive specific features:
   - `directives/sync_candidates.md`
   - `directives/generate_brief.md`
   - `directives/manifesto_diff.md`
   - `directives/squad_calendar_share.md`

## Outputs
- Deployed Cloud Run URL (https-{service}-{hash}.run.app)
- 100%-coverage pytest suite, green CI badge
- README with demo URL, problem statement, architecture diagram, build time
- 90-second demo recording as fallback

## Locked feature scope
1. **My Election** — state timeline (Gemini Search Grounding) + ECI registration deeplink
2. **Candidate Snapshot** — Gemini brief over Sheet/MyNeta data, with source citations
3. **Manifesto Diff** — Gemini side-by-side party manifesto comparison with page citations
4. **Voting Squad** — Sheet-backed group accountability + Calendar URL-spec + WhatsApp `wa.me` share

Cross-cutting: 5 native languages (English, Hindi, Tamil, Bengali, Marathi) + Gemini auto-translate fallback for any other Indian language. TTS read-aloud, mic input via Web Speech API.

## Edge cases & rules
- **No PII storage**: EPIC ID never sent server-side. Use ECI deeplinks for any voter-ID action.
- **No Search Grounding for facts about people**: defamation risk. Candidate facts come from MyNeta mirror only.
- **DEMO_MODE flag**: when true, all external calls return canned data after 2s timeout. Used during stage demo.
- **Cache-bust assets** via `?v={{ build_id }}` from day one (per playbook — saves 30+ min of "why isn't redeploy taking" debugging).
- **One LLM call per user action**, structured output via Gemini `responseSchema`.
- **No OAuth**: Calendar uses URL-spec (`render?action=TEMPLATE&...`), share uses `wa.me/?text=`.
- **Test coverage gate**: 100% enforced via `pyproject.toml` `fail_under=100`.

## What we are NOT building (in README, prominently)
Live election results · exit polls · social/news feed · debate transcripts · winner predictions · election betting (illegal in India) · WhatsApp bot (stretch) · push notifications (stretch) · OAuth Google Calendar (stretch — `.ics`/URL-spec is enough)

## Demo arc (90 seconds — written before code, per playbook rule)
| t | Action |
|---|---|
| 0–5s | Open URL with `?lang=hi&demo=1` — Hindi pre-selected |
| 5–20s | Manifesto Diff loads sample (DMK vs ADMK, "women's safety") with page citations |
| 20–35s | Candidate Snapshot for Chepauk constituency, brief in Hindi, MyNeta source link |
| 35–55s | Create Voting Squad → "Add to Calendar" opens prefilled Google Calendar tab |
| 55–75s | "Share to WhatsApp" opens prefilled `wa.me` tab |
| 75–90s | Mic input: "मेरा बूथ कहाँ है?" → polling station card with Maps deeplink |

## Self-anneal log
(append learnings here as they come)
