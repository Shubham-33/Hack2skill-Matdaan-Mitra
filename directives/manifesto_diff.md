# Manifesto Diff — Directive

## Goal
Side-by-side comparison of two party manifestos on a chosen issue, with page-number citations to the source PDFs. This is the demo's "wow" moment — lead with it.

## Inputs
- `party_a`, `party_b` (slugs matching files in `web/data/manifestos/`)
- `issue` (one of: `jobs`, `women_safety`, `climate`, `education`, `healthcare`)
- `lang` (defaults to `en`)

## Tools
- `web/app.py` route `GET /api/manifesto-diff?a=...&b=...&issue=...&lang=...`
- 4–6 pre-loaded manifesto PDFs in `web/data/manifestos/<state>/<party>.pdf`
- Gemini 2.5 Flash with PDF input (Gemini accepts PDFs via `inline_data` base64), responseSchema:
  ```json
  {
    "type": "object",
    "properties": {
      "issue": {"type": "string"},
      "rows": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "point": {"type": "string"},
            "party_a_position": {"type": "string"},
            "party_a_page": {"type": "integer"},
            "party_b_position": {"type": "string"},
            "party_b_page": {"type": "integer"}
          },
          "required": ["point", "party_a_position", "party_b_position"]
        }
      }
    }
  }
  ```

## Outputs
- JSON with 3–5 comparison rows, each with positions and page citations
- Frontend renders as a 2-column table with PDF page-deeplinks (`<file>.pdf#page=N`)

## Edge cases & rules
- **No 2026 election in the picked state** → return `{ "rows": [], "note": "No active state election in 2026" }`
- **PDF too large** (Gemini Flash limit ~50MB): pre-extract relevant chapters during data prep, store smaller per-issue PDFs
- **Hallucinated page numbers**: low risk with PDF input + responseSchema, but UI shows "page N" as-claimed; user can click through to verify
- **DEMO_MODE**: return canned diff for `dmk vs aiadmk on women_safety` in Hindi
- **Cache by `(party_a, party_b, issue, lang)`** in memory — these 4 manifestos × 5 issues × 5 langs = 500 max combinations

## Self-anneal log
- (none yet)
