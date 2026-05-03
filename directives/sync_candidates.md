# Sync Candidates — Directive

> **Updated 2026-05-03**: Pivoted from Vonter mirror (archived, MyNeta ToU issues) to OpenCity dataset (Public Domain license, 2810 candidates across 23 states).

## Goal
Maintain a local `web/data/candidates.json` file containing all Lok Sabha 2024 candidate data, sourced from OpenCity's public-domain affidavit dataset. Ships as a static asset with the Cloud Run deploy.

## Inputs
- OpenCity CSV (versioned, public domain, ECI-sourced):
  `https://data.opencity.in/dataset/f487d745-3cc0-4062-84cb-59d0a12f04f8/resource/1da58e70-f8dd-4bdd-bbd9-863d2246198c/download/a9f67a1e-186b-48a9-80de-f1359c2b0326.csv`
- CKAN dataset metadata API (for license verification):
  `https://data.opencity.in/api/3/action/package_show?id=parliamentary-elections-2024-affidavits`

## Tools / scripts
- `execution/sync_candidates.py` — single-shot script:
  1. Download CSV (HTTP GET, cache to `.tmp/affidavits_2024.csv`)
  2. Parse via stdlib `csv.DictReader`
  3. Group by `State → Constituency → [candidates]`
  4. Write `web/data/candidates.json`
  5. Print summary stats

## Outputs
- `web/data/candidates.json` shape:
  ```json
  {
    "source": "OpenCity Parliamentary Elections 2024 Affidavits (Public Domain)",
    "source_url": "https://data.opencity.in/dataset/parliamentary-elections-2024-affidavits",
    "synced_at": "2026-05-03T16:30:00Z",
    "total_candidates": 2810,
    "states": {
      "TAMIL NADU": {
        "CHENNAI CENTRAL": [
          {
            "name": "Dayanithi Maran",
            "party": "DMK",
            "criminal_cases": 0,
            "education": "Graduate Professional",
            "age": 59,
            "total_assets_inr": 38500000,
            "liabilities_inr": 12000000,
            "winner": true,
            "comment": ""
          }
        ]
      }
    }
  }
  ```
- Stdout summary: total candidates, states covered, top constituencies by count

## Edge cases & rules
- **CSV column drift**: pin to schema `[Candidate, Party, Criminal Cases, Education, Age, Total Assets, Liabilities, Winner, Constituency, State, District, Year, House, Comment]`. Fail loud if any column missing.
- **Numeric parsing**: assets/liabilities are large ints, `Criminal Cases` integer or empty. Coerce empty → 0 for cases, → null for assets.
- **Encoding**: read CSV as UTF-8 with `errors="replace"` for safety.
- **Constituency normalization**: strip trailing whitespace, uppercase consistently for keys; preserve original case in display fields.
- **No PDF download** — we only need the summary CSV. PDFs stay on OpenCity (we link to them via search params).
- **License attribution**: README and footer must credit OpenCity + ECI as source.

## Self-anneal log
- 2026-05-03: Pivoted from `Vonter/india-election-affidavits` (archived due to MyNeta Terms of Use restrictions) to OpenCity. Original source ECI is public domain, OpenCity is licensed Open Definition–compliant. Defensible to judges.
