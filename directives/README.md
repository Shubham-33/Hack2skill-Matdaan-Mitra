# Directives

Each `.md` file here is an SOP — natural-language instructions for the orchestrator (the agent).

A directive should specify:
- **Goal** — what success looks like
- **Inputs** — what the orchestrator needs before starting
- **Tools / scripts** — which `execution/*.py` scripts to call, in what order
- **Outputs** — where results go (Sheet, Slide, email, etc.)
- **Edge cases** — known failure modes, API limits, retries, things learned the hard way

Treat directives as living documents: when you discover a new constraint or a better path, update the directive so the next run benefits.
