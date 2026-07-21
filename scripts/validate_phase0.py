#!/usr/bin/env python3
"""Validate Phase 0 corpus manifest + golden eval gates.

Usage:
  python scripts/validate_phase0.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "corpus" / "manifest.yaml"
RAW_DIR = ROOT / "corpus" / "raw"
GOLDEN_PATH = ROOT / "evals" / "golden.jsonl"

CONTROLLED_TAGS = {
    "single_doc",
    "yoy_metric",
    "narrative",
    "multi_hop",
    "table_heavy",
    "bilingual",
    "year_collision",
}


def load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_golden() -> list[dict]:
    items = []
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"golden.jsonl line {i}: {exc}") from exc
    return items


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not MANIFEST_PATH.exists():
        errors.append(f"missing {MANIFEST_PATH}")
        print("FAIL")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1

    manifest = load_manifest()
    reports = manifest.get("reports") or []
    by_id = {r["id"]: r for r in reports}
    filenames = {r.get("filename") for r in reports if r.get("filename")}

    present = [r for r in reports if r.get("status") == "present"]
    for r in present:
        fn = r.get("filename")
        if not fn:
            errors.append(f"present report {r['id']} missing filename")
            continue
        path = RAW_DIR / fn
        if not path.exists():
            errors.append(f"present report {r['id']} file missing: {path}")
        elif path.read_bytes()[:5] != b"%PDF-":
            errors.append(f"present report {r['id']} is not a PDF: {path}")
        sha = r.get("sha256")
        if not sha:
            warnings.append(f"present report {r['id']} has no sha256")

    annual_fin = [
        r
        for r in present
        if r.get("report_type") in {"annual", "financials"}
    ]
    if len({(r["year"], r["report_type"]) for r in annual_fin}) < 2:
        errors.append(
            "need multiple years of present annual and/or financials "
            f"(currently {len(present)} present of {len(reports)})"
        )

    if not GOLDEN_PATH.exists():
        errors.append(f"missing {GOLDEN_PATH}")
    else:
        items = load_golden()
        n = len(items)
        if not 20 <= n <= 40:
            errors.append(f"golden count {n} not in [20, 40]")

        tagged = 0
        has_table = False
        has_year_collision = False
        has_bilingual = False
        ids: set[str] = set()

        for item in items:
            iid = item.get("id")
            if not iid:
                errors.append("golden item missing id")
                continue
            if iid in ids:
                errors.append(f"duplicate golden id: {iid}")
            ids.add(iid)

            for field in ("question", "tags", "expected_evidence", "notes"):
                if field not in item:
                    errors.append(f"{iid}: missing field {field}")

            tags = item.get("tags") or []
            if not isinstance(tags, list):
                errors.append(f"{iid}: tags must be a list")
                tags = []
            unknown = set(tags) - CONTROLLED_TAGS
            if unknown:
                errors.append(f"{iid}: unknown tags {sorted(unknown)}")
            if tags:
                tagged += 1
            if "table_heavy" in tags:
                has_table = True
            if "year_collision" in tags:
                has_year_collision = True
            if "bilingual" in tags:
                has_bilingual = True

            ev = item.get("expected_evidence") or {}
            if not isinstance(ev, dict) or "years" not in ev:
                errors.append(f"{iid}: expected_evidence.years required")
            else:
                years = ev["years"]
                if not isinstance(years, list) or not years:
                    errors.append(f"{iid}: expected_evidence.years must be non-empty list")

            for rid in ev.get("report_ids") or []:
                if rid not in by_id:
                    errors.append(f"{iid}: report_id {rid} not in manifest")
            for fn in ev.get("filenames") or []:
                if fn not in filenames:
                    errors.append(f"{iid}: filename {fn} not in manifest")

        if n:
            rate = tagged / n
            if rate < 0.8:
                errors.append(f"tagged rate {rate:.0%} < 80%")
        if not has_table:
            errors.append("missing hard case tag: table_heavy")
        if not has_year_collision:
            errors.append("missing hard case tag: year_collision")
        if not has_bilingual:
            readme = ROOT / "evals" / "README.md"
            text = readme.read_text(encoding="utf-8") if readme.exists() else ""
            if "bilingual" not in text.lower() or "gap" not in text.lower():
                errors.append(
                    "no bilingual golden item and evals/README.md missing bilingual gap note"
                )
            else:
                warnings.append("no bilingual golden item; gap documented in evals/README.md")

    print("Phase 0 validation")
    print(f"  manifest reports: {len(reports)} ({len(present)} present)")
    if GOLDEN_PATH.exists():
        print(f"  golden items: {len(load_golden())}")
    for w in warnings:
        print(f"  WARN: {w}")
    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
