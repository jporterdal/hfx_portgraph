#!/usr/bin/env python3
"""Spike CLI: run the full detect -> crop -> VLM-extract pipeline, writing kpi_facts.jsonl."""

from __future__ import annotations

import argparse

from hfx_portgraph.kpi_spike import run_spike


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract chart-borne KPI facts via a local VLM")
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--page", type=int, action="append", dest="pages")
    args = parser.parse_args(argv)

    out = run_spike(args.report_id, pages=args.pages)
    print(f"✓ wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
