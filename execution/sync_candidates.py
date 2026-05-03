"""Sync Lok Sabha 2024 candidate affidavits from OpenCity (Public Domain) into web/data/candidates.json.

Runs as a one-shot script. See directives/sync_candidates.md for the full SOP.

Usage:
    python3 execution/sync_candidates.py
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CSV_URL: Final[str] = (
    "https://data.opencity.in/dataset/f487d745-3cc0-4062-84cb-59d0a12f04f8/"
    "resource/1da58e70-f8dd-4bdd-bbd9-863d2246198c/download/"
    "a9f67a1e-186b-48a9-80de-f1359c2b0326.csv"
)
DATASET_PAGE: Final[str] = "https://data.opencity.in/dataset/parliamentary-elections-2024-affidavits"

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
TMP_CSV: Final[Path] = REPO_ROOT / ".tmp" / "affidavits_2024.csv"
OUTPUT_JSON: Final[Path] = REPO_ROOT / "web" / "data" / "candidates.json"

EXPECTED_COLUMNS: Final[set[str]] = {
    "Candidate", "Party", "Criminal Cases", "Education", "Age",
    "Total Assets", "Liabilities", "Winner", "Constituency",
    "State", "District", "Year", "House", "Comment",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _to_int(value: str | None) -> int | None:
    """Parse a CSV cell to int, returning None for blank/non-numeric."""
    if value is None:
        return None
    cleaned = value.strip().replace(",", "")
    if not cleaned or cleaned.lower() in {"na", "n/a", "none"}:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _normalize_key(value: str) -> str:
    """Normalize state/constituency for use as a dict key."""
    return " ".join(value.strip().upper().split())


def _candidate_record(row: dict[str, str]) -> dict:
    """Project one CSV row into the shape we serve to the frontend."""
    return {
        "name": row["Candidate"].strip(),
        "party": row["Party"].strip(),
        "criminal_cases": _to_int(row["Criminal Cases"]) or 0,
        "education": row["Education"].strip(),
        "age": _to_int(row["Age"]),
        "total_assets_inr": _to_int(row["Total Assets"]),
        "liabilities_inr": _to_int(row["Liabilities"]),
        "winner": row["Winner"].strip().lower() == "yes",
        "comment": row["Comment"].strip(),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def download_csv(url: str, dest: Path) -> None:
    """Download CSV to local cache. Idempotent — overwrites."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"→ Downloading {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (controlled URL)
        dest.write_bytes(resp.read())
    print(f"  wrote {dest} ({dest.stat().st_size:,} bytes)")


def parse_csv(path: Path) -> dict[str, dict[str, list[dict]]]:
    """Read the affidavits CSV, return nested dict: state → constituency → [candidate]."""
    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not EXPECTED_COLUMNS.issubset(set(reader.fieldnames)):
            missing = EXPECTED_COLUMNS - set(reader.fieldnames or [])
            raise RuntimeError(f"CSV schema drift: missing columns {missing}")

        states: dict[str, dict[str, list[dict]]] = {}
        for row in reader:
            state = _normalize_key(row["State"])
            constituency = _normalize_key(row["Constituency"])
            if not state or not constituency:
                continue
            states.setdefault(state, {}).setdefault(constituency, []).append(_candidate_record(row))

    # Stable ordering for diffability
    return {
        s: {c: sorted(cands, key=lambda x: x["name"]) for c, cands in sorted(consts.items())}
        for s, consts in sorted(states.items())
    }


def write_output(data: dict[str, dict[str, list[dict]]], dest: Path) -> None:
    total = sum(len(c) for s in data.values() for c in s.values())
    payload = {
        "source": "OpenCity Parliamentary Elections 2024 Affidavits (Public Domain, sourced from ECI)",
        "source_url": DATASET_PAGE,
        "synced_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "total_candidates": total,
        "states": data,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {dest} ({dest.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> int:
    download_csv(CSV_URL, TMP_CSV)
    data = parse_csv(TMP_CSV)
    write_output(data, OUTPUT_JSON)

    total = sum(len(c) for s in data.values() for c in s.values())
    constituencies = sum(len(c) for c in data.values())
    print(f"\n✅ Synced {total:,} candidates across {len(data)} states / {constituencies:,} constituencies")
    print(f"   Top 5 by candidate count:")
    top = sorted(((s, sum(len(cs) for cs in d.values())) for s, d in data.items()), key=lambda x: -x[1])[:5]
    for s, n in top:
        print(f"     {s}: {n}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
