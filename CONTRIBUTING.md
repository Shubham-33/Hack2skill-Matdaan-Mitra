# Contributing to Matdaan Mitra

Thanks for your interest. This document keeps the contributor experience predictable.

## Architecture (read first)

The project uses a 3-layer pattern from `CLAUDE.MD`:

- `directives/` — natural-language SOPs (the *what*). One Markdown file per pipeline.
- `execution/` — deterministic Python scripts (the *how*). They do scraping, parsing, file writes.
- `web/` — Flask app that serves the chat UI. Reads pre-built data files from `web/data/`.

If you're adding a new pipeline, write the directive first. The directive should specify goals, inputs, tools, outputs, and known edge cases. Then write the execution script that follows it.

## Local setup

```bash
# Python 3.10+ required
python3.10 -m venv .venv
.venv/bin/pip install -r web/requirements.txt -r web/requirements-dev.txt

# Get a Gemini key from https://aistudio.google.com/app/apikey
cp .env.example .env
# Open .env and set GOOGLE_AI_API_KEY=AIzaSy...

# One-shot data sync (downloads OpenCity affidavits + manifestos)
.venv/bin/python execution/sync_candidates.py
.venv/bin/python execution/sync_manifestos.py

# Run
.venv/bin/python web/app.py
# → http://localhost:5050
```

## Quality gates

All PRs must pass these before merging:

| Gate | Command | What it checks |
|---|---|---|
| Tests | `cd web && pytest` | All tests pass |
| Coverage | `pytest` (uses `pyproject.toml`) | 100.00% — gate enforced via `fail_under = 100` |
| Lint | `ruff check web/app.py web/tests/` | No style/import/safety violations |
| CI | GitHub Actions | Runs the above on every push to `main` and every PR |

If you add a new code path, add a test that exercises it. Tests live in `web/tests/`.

## Coding conventions

- Type hints on every public function signature.
- Docstrings on every public function. Format: one-line summary, then optional details + `:param:` lines for non-obvious args.
- Section banners (`# --- Foo ---`) in `app.py` to keep navigation easy.
- No `print()` for app logging — use Flask's `app.logger` if you really need it.
- Don't catch `Exception:` blanket — name the specific exception types you handle.
- `# pragma: no cover` is reserved for genuinely untestable lines (e.g. `__main__` blocks, missing-API-key guards). If you reach for it, justify in a code comment.

## Commit style

- Use the imperative mood: "Add X" not "Added X" or "Adds X".
- First line ≤ 72 chars. Body explains *why*, not *what*.
- One logical change per commit.

## Adding a new chat intent

1. Add the slug to the `enum` in `_CHAT_INTENT_SCHEMA`.
2. Document it in `_CHAT_SYSTEM_PROMPT` so the classifier knows when to pick it.
3. Add a branch in `_dispatch_intent()` that does the work.
4. Add at least 2 tests in `tests/test_chat.py`: one happy path, one error/edge case.
5. Update `api_suggestions` if it's user-facing.

## Adding a new language

1. Add the language code + display name to `SUPPORTED_LANGS` in `app.py`.
2. Add suggested prompts to the `by_lang` dict in `api_suggestions`.
3. Add the BCP-47 mapping to `LANG_TO_BCP47` in `web/static/app.js` (for TTS / mic).
4. The classifier and brief generator handle any Indian language natively via Gemini — no template work needed.

## Deploying

```bash
# In Cloud Shell (gcloud preinstalled)
cd ~/Hack2skill-Matdaan-Mitra && git pull && cd web && \
./deploy.sh <PROJECT_ID> <GEMINI_API_KEY>
```

Default region is `asia-south1` (Mumbai). The script handles Secret Manager + IAM bindings.

## Data sources

We use only **Public Domain** data (OpenCity's rebundle of ECI candidate affidavits and party manifestos). We do not redistribute MyNeta data — their Terms of Use prohibit it, and the ECI source is the authoritative public record anyway.

If you add a new data source, document it in the relevant directive and verify the license allows redistribution.

## Security expectations

- Never commit `.env`, `credentials.json`, or `token.json`. The `.gitignore` blocks them.
- Never paste API keys in PR descriptions, issue comments, or commit messages.
- If a key leaks (in chat logs, screenshots, public commits), rotate it at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
- User-supplied strings reach Gemini prompts directly; the schema-restricted output and `escapeHtml` on the frontend keep this safe, but always prefer structured outputs over free text when generating UI.

## Reporting bugs

Open a GitHub issue with:
1. Browser / OS / device.
2. Steps to reproduce.
3. Expected vs actual behavior.
4. Console error (DevTools → Console) if applicable.

Sensitive issues (e.g. security): email the maintainer instead of opening a public issue.
