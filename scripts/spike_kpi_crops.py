#!/usr/bin/env python3
"""Spike CLI: source a figure crop for each design-heavy page (Docling -> Marker -> render)."""

from __future__ import annotations

import argparse

from hfx_portgraph.kpi_spike import detect_design_heavy_pages, source_crop_for_page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source figure crops for design-heavy pages")
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--page", type=int, action="append", dest="pages")
    args = parser.parse_args(argv)

    flagged = detect_design_heavy_pages(args.report_id)
    if args.pages:
        flagged = [f for f in flagged if f.page in args.pages]

    for f in flagged:
        crop = source_crop_for_page(args.report_id, f.page)
        print(f"page {f.page}: source={crop.source} path={crop.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
