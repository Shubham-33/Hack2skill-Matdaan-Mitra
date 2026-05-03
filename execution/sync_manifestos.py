"""Download + extract text from party manifesto PDFs (OpenCity, Public Domain).

PDFs are downloaded on first run if missing; not committed to git (see .gitignore).
We extract per-page so Gemini can cite "page N" in comparison output. Text is trimmed
to keep the JSON under 1MB and Gemini prompts within budget.

Usage:
    python3 execution/sync_manifestos.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.request import urlopen

from pypdf import PdfReader

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANIFESTOS_DIR: Final[Path] = REPO_ROOT / "web" / "data" / "manifestos"
OUTPUT_JSON: Final[Path] = REPO_ROOT / "web" / "data" / "manifestos.json"

# slug → display metadata + canonical party URL + OpenCity Public Domain PDF URL
PARTIES: Final[dict[str, dict]] = {
    "bjp": {
        "name": "Bharatiya Janata Party",
        "short": "BJP",
        "color": "#FF9933",
        "source_url": "https://www.bjp.org/manifesto",
        "pdf_url": "https://data.opencity.in/dataset/76e54184-f294-44e4-a40c-8594ccb410c8/resource/6210fb78-c1c3-4700-a61f-ed01daee9aff/download/7377fce3-f32d-4dba-8d1c-4969c25a3add.pdf",
    },
    "inc": {
        "name": "Indian National Congress",
        "short": "INC",
        "color": "#0078D7",
        "source_url": "https://manifesto.inc.in/",
        "pdf_url": "https://data.opencity.in/dataset/76e54184-f294-44e4-a40c-8594ccb410c8/resource/e2a62a20-74a6-472e-ab7e-79f610235893/download/8a16787a-0134-4ac4-9fde-d17506675642.pdf",
    },
    "dmk": {
        "name": "Dravida Munnetra Kazhagam",
        "short": "DMK",
        "color": "#E03A1A",
        "source_url": "https://www.dmk.in/en/resources/manifesto/",
        "pdf_url": "https://data.opencity.in/dataset/76e54184-f294-44e4-a40c-8594ccb410c8/resource/c86a0519-1a32-407c-8381-41659734f9a2/download/a7964b61-ee79-4f84-9e1b-e3e28be52e04.pdf",
    },
    "cpim": {
        "name": "Communist Party of India (Marxist)",
        "short": "CPI(M)",
        "color": "#C00000",
        "source_url": "https://cpim.org/documents/election-manifesto",
        "pdf_url": "https://data.opencity.in/dataset/76e54184-f294-44e4-a40c-8594ccb410c8/resource/c04b71e0-5941-4684-8b7e-c58cd713081d/download/2bc55e52-18f0-42fa-b228-56e85ec55de5.pdf",
    },
}

# Pages per manifesto we ship (most are 50-100 pages). We keep all pages to
# preserve citation accuracy, but trim each page's text.
MAX_CHARS_PER_PAGE: Final[int] = 1500
WHITESPACE_RE: Final[re.Pattern] = re.compile(r"\s+")


def _clean(text: str) -> str:
    """Normalize whitespace, drop control chars, trim length."""
    cleaned = WHITESPACE_RE.sub(" ", text or "").strip()
    return cleaned[:MAX_CHARS_PER_PAGE]


def extract(pdf_path: Path) -> list[str]:
    """Return one cleaned string per page."""
    reader = PdfReader(str(pdf_path))
    return [_clean(page.extract_text() or "") for page in reader.pages]


def download_if_missing(url: str, dest: Path) -> None:
    """Fetch url → dest unless dest already exists."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ downloading {url}")
    with urlopen(url, timeout=60) as resp:  # noqa: S310 (controlled URL)
        dest.write_bytes(resp.read())


def main() -> int:
    out = {
        "synced_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "source": "OpenCity Parliamentary Elections 2024 Manifestos (Public Domain)",
        "source_url": "https://data.opencity.in/dataset/parliamentary-elections-2024-manifestos",
        "parties": {},
    }
    for slug, meta in PARTIES.items():
        pdf = MANIFESTOS_DIR / f"{slug}.pdf"
        download_if_missing(meta["pdf_url"], pdf)
        pages = extract(pdf)
        non_empty = sum(1 for p in pages if p)
        # Strip pdf_url from the published payload — runtime app doesn't need it
        meta_pub = {k: v for k, v in meta.items() if k != "pdf_url"}
        out["parties"][slug] = {
            **meta_pub,
            "slug": slug,
            "page_count": len(pages),
            "non_empty_pages": non_empty,
            "pages": pages,
        }
        print(f"  {slug}: {len(pages)} pages, {non_empty} non-empty, {sum(len(p) for p in pages):,} chars")

    OUTPUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    size_mb = OUTPUT_JSON.stat().st_size / 1024 / 1024
    print(f"\n✅ Wrote {OUTPUT_JSON.relative_to(REPO_ROOT)} ({size_mb:.2f} MB) covering {len(out['parties'])} parties")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
