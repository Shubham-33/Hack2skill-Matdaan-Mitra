# Generate Candidate Brief — Directive

## Goal
Given a candidate row from the `Candidates` sheet, produce a neutral 3-bullet brief in the user's chosen language, citing the MyNeta source URL.

## Inputs
- Path or query: `state`, `constituency`, `candidate_name`
- `lang` query param (default `en`)
- Sheet row fetched server-side

## Tools
- `web/app.py` route `GET /api/brief?state=...&constituency=...&candidate=...&lang=...`
- Gemini 2.5 Flash via REST (`requests`) with structured output:
  ```json
  {
    "type": "object",
    "properties": {
      "background": {"type": "string"},
      "disclosed_assets": {"type": "string"},
      "pending_cases": {"type": "string"},
      "source_url": {"type": "string"}
    },
    "required": ["background", "disclosed_assets", "pending_cases", "source_url"]
  }
  ```

## Outputs
- JSON: `{ background, disclosed_assets, pending_cases, source_url, lang, generated_at }`
- HTTP 200 on success, 404 if candidate not in sheet, 503 on Gemini timeout (with retry-after)

## Edge cases & rules
- **Always cite as filed in affidavit**, never "convicted" or "criminal" (legal/defamation risk). Pending case wording: "X cases declared in 2024 affidavit". Use the playbook's neutral framing.
- **Lang fallback**: if requested lang isn't in the 5 native, ask Gemini to generate in that language directly (1M context handles it). Cache by `(candidate_id, lang)` in memory dict (per-process, fine for hackathon).
- **Gemini timeout 8s** — fall back to "Brief unavailable, see source affidavit" + source link.
- **DEMO_MODE**: return canned brief for the demo candidate in <100ms (skip Gemini).
- **Single LLM call** per request — no chain-of-thought, no retry on bad JSON (responseSchema makes it parseable).

## Self-anneal log
- (none yet)
