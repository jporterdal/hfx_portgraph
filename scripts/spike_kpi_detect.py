#!/usr/bin/env python3
"""Spike CLI: flag design-heavy pages from already-parsed Docling artifacts."""

from __future__ import annotations

import argparse
import json

from hfx_portgraph.kpi_spike import detect_design_heavy_pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect design-heavy pages")
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    flagged = detect_design_heavy_pages(args.report_id)

    if args.json:
        print(json.dumps([f.__dict__ for f in flagged], indent=2))
        return 0

    print(f"{len(flagged)} design-heavy page(s) flagged in {args.report_id}:\n")
    for f in flagged:
        headings = "; ".join(f.headings) or "(none)"
        print(f"  page {f.page}: {f.reason}")
        print(f"    headings: {headings}")
        print(f"    pictures={f.picture_count} words={f.word_count}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
