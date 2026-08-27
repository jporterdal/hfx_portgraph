#!/usr/bin/env python3
"""Task 5.1 -- leave-one-report-out sanity check for strip-page-furniture.

Point 1 (parse.py's fused furniture signal) and Point 2 (chunk.py's running-
header fold) both use fixed, relative-threshold constants documented in
design.md -- they are not fit/tuned per-report, so there is no literal
train/test split to hold out. What this script checks instead is the
generalization question tasks.md 5.1 actually cares about: does the same
fixed heuristic produce sane, same-order-of-magnitude behavior on every one
of the 8 reports, or does it degenerate (near-0% or near-100% stripped, or a
report whose signal composition looks nothing like the rest) on any single
report -- which would be a sign the thresholds were implicitly overfit to
the two reports (2020_annual_en, 2021_annual_en) the investigation in
design.md's Context focused most closely on.

For each report, "holding it out" means: compute its stats, then compare
against the mean/stdev of the *other 7* reports' stats -- flagging it only
if it's an outlier relative to its peers, not against a threshold tuned on
itself.

Usage: .venv/bin/python scripts/leave_one_out_check.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from hfx_portgraph.chunk import _parse_sections, _split_heading_stream
from hfx_portgraph.paths import CHUNKS_DIR, PARSED_DIR, v1_present_reports

OUTLIER_Z = 2.0  # flag a report whose stat sits > this many stdevs from the other 7's mean


def _signal_composition(items_path: Path) -> dict:
    counts = {"furniture": 0, "kept": 0}
    signal_combo_counts: dict[str, int] = {}
    with items_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            counts[rec["classification"]] = counts.get(rec["classification"], 0) + 1
            if rec["classification"] == "furniture":
                key = "+".join(sorted(rec["signals_fired"]))
                signal_combo_counts[key] = signal_combo_counts.get(key, 0) + 1
    return {"counts": counts, "furniture_signal_combos": signal_combo_counts}


def _fold_stats(report_id: str) -> dict:
    md_path = PARSED_DIR / report_id / "document.md"
    markdown = md_path.read_text(encoding="utf-8")
    raw_sections = _split_heading_stream(markdown)
    folded_sections = _parse_sections(markdown)
    raw_count = max(len(raw_sections) - 1, 1)  # exclude preamble
    folded_count = max(len(folded_sections) - 1, 1)
    return {
        "raw_headings": raw_count,
        "folded_parents": folded_count,
        "fold_ratio": 1 - (folded_count / raw_count),
    }


def main() -> int:
    report_ids = [r["id"] for r in v1_present_reports()]
    per_report: dict[str, dict] = {}

    for rid in report_ids:
        meta = json.loads((PARSED_DIR / rid / "meta.json").read_text(encoding="utf-8"))
        considered = meta["items_considered"]
        stripped = meta["items_stripped_as_furniture"]
        composition = _signal_composition(PARSED_DIR / rid / "items.jsonl")
        fold = _fold_stats(rid)
        per_report[rid] = {
            "items_considered": considered,
            "items_stripped": stripped,
            "stripped_frac": stripped / considered if considered else 0.0,
            "furniture_signal_combos": composition["furniture_signal_combos"],
            **fold,
        }

    flagged: list[str] = []
    for metric in ("stripped_frac", "fold_ratio"):
        for rid in report_ids:
            others = [per_report[o][metric] for o in report_ids if o != rid]
            mean = statistics.mean(others)
            stdev = statistics.pstdev(others) or 1e-9
            z = (per_report[rid][metric] - mean) / stdev
            per_report[rid][f"{metric}_z_vs_other7"] = round(z, 2)
            if abs(z) > OUTLIER_Z:
                flagged.append(f"{rid}: {metric} z={z:.2f} (value={per_report[rid][metric]:.3f}, other-7 mean={mean:.3f})")

    print(f"{'report':22s} {'stripped%':>10s} {'z(strip)':>9s} {'raw_h':>6s} {'folded':>7s} {'fold%':>7s} {'z(fold)':>8s}")
    for rid in report_ids:
        s = per_report[rid]
        print(
            f"{rid:22s} {s['stripped_frac']*100:9.1f}% {s['stripped_frac_z_vs_other7']:9.2f} "
            f"{s['raw_headings']:6d} {s['folded_parents']:7d} {s['fold_ratio']*100:6.1f}% "
            f"{s['fold_ratio_z_vs_other7']:8.2f}"
        )

    print()
    if flagged:
        print(f"FLAGGED ({len(flagged)}) -- outlier relative to other 7 reports (|z| > {OUTLIER_Z}):")
        for f in flagged:
            print(f"  - {f}")
    else:
        print(f"No report is an outlier relative to the other 7 (|z| <= {OUTLIER_Z}) on either metric.")

    out_path = Path("scripts/scratch/leave_one_out_check.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"per_report": per_report, "flagged": flagged}, indent=2), encoding="utf-8")
    print(f"\nFull record: {out_path}")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
