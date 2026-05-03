# Execution

Deterministic Python scripts. Each script does one well-scoped thing — fetch, transform, write. No probabilistic logic here; that lives with the orchestrator.

Conventions:
- Scripts read config from `.env` (use `python-dotenv` or `os.environ`).
- Inputs come from CLI args or stdin; outputs go to `.tmp/`, stdout, or a cloud destination (Sheets, Slides, email).
- Exit non-zero on failure with a clear message — the orchestrator reads stderr to self-anneal.
- Prefer batch endpoints over per-item calls. Respect rate limits.
