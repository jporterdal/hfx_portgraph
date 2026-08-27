#!/usr/bin/env python3
"""Frequency-scan contamination measurement for strip-page-furniture.

Counts child chunks containing at least one line that repeats >=3 times
verbatim (digit-normalized) within its report's parsed markdown. Used to
measure before/after impact -- see
openspec/changes/strip-page-furniture/design.md and tasks.md 5.2.

Usage: python scripts/measure_furniture_contamination.py [parsed_dir] [chunks_dir]
Defaults to the live corpus/parsed and corpus/chunks directories.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from hfx_portgraph.paths import CHUNKS_DIR, PARSED_DIR, v1_present_reports

_DIGIT_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


def _normalize_line(line: str) -> str:
    t = line.strip().lower()
    t = _DIGIT_RE.sub("#", t)
    t = _WS_RE.sub(" ", t)
    return t


def repeated_lines(markdown: str, min_repeats: int = 3, min_len: int = 15) -> set[str]:
    """Lines repeating >=min_repeats times verbatim (digit-normalized).

    Excludes markdown artifacts that repeat legitimately and aren't page
    furniture (image placeholders, table rows) and short generic phrases
    (`min_len`) that repeat coincidentally rather than as boilerplate -- the
    same false-positive class `design.md` names for "Director".
    """
    counts: Counter[str] = Counter()
    for line in markdown.splitlines():
        norm = _normalize_line(line)
        if len(norm) < min_len:
            continue
        if norm.startswith("<!--") or norm.startswith("|"):
            continue
        counts[norm] += 1
    return {line for line, c in counts.items() if c >= min_repeats}


def measure(report_ids: list[str], parsed_dir: Path, chunks_dir: Path) -> dict:
    total_child = 0
    contaminated_child = 0
    per_report: dict[str, dict] = {}
    for rid in report_ids:
        md_path = parsed_dir / rid / "document.md"
        chunks_path = chunks_dir / f"{rid}.jsonl"
        if not md_path.exists() or not chunks_path.exists():
            continue
        markdown = md_path.read_text(encoding="utf-8")
        repeats = repeated_lines(markdown)
        n_child = 0
        n_bad = 0
        with chunks_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("role") != "child":
                    continue
                n_child += 1
                text_lines = [_normalize_line(l) for l in rec["text"].splitlines()]
                if any(l in repeats for l in text_lines if l):
                    n_bad += 1
        per_report[rid] = {
            "child_chunks": n_child,
            "contaminated": n_bad,
            "pct": round(100 * n_bad / n_child, 1) if n_child else 0.0,
        }
        total_child += n_child
        contaminated_child += n_bad
    return {
        "per_report": per_report,
        "total_child_chunks": total_child,
        "total_contaminated": contaminated_child,
        "pct": round(100 * contaminated_child / total_child, 1) if total_child else 0.0,
    }


def main(argv: list[str]) -> int:
    parsed_dir = Path(argv[1]) if len(argv) > 1 else PARSED_DIR
    chunks_dir = Path(argv[2]) if len(argv) > 2 else CHUNKS_DIR
    report_ids = [r["id"] for r in v1_present_reports()]
    result = measure(report_ids, parsed_dir, chunks_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
