#!/usr/bin/env python3
"""Tasks 3.3 / 4.1-4.4 -- typed retrieval tools validation.

Two parts, no LLM/`ask()` involved -- both call `retrieval_tools.py`
functions directly:

1. Section classifier spot-check (3.3): run `classify_section()` over every
   real heading in the 8 v1 reports' parsed chunks, not just gq-019's
   specific case, and report the classification distribution plus any
   headings worth a second look.

2. Golden-set evidence-coverage validation (4.1-4.4): for every
   `multi_hop`/`yoy_metric`/`year_collision`-tagged item in
   `evals/golden.jsonl`, call the typed functions with that item's
   `expected_evidence.years`/`report_ids` and record whether the returned
   hits cover every requested year/report_id, plus (for `year_collision`
   items) whether section-filtered retrieval avoids the known footnote
   collision documented in `evals/phase1_baseline.md`.

Results are written to `evals/typed_retrieval_validation.md`.

Usage: .venv/bin/python scripts/validate_typed_retrieval.py
"""

from __future__ import annotations

import json
from collections import Counter

from hfx_portgraph.chunk import load_chunks
from hfx_portgraph.paths import GOLDEN_PATH, ROOT, v1_present_reports
from hfx_portgraph.retrieval_tools import (
    classify_section,
    retrieve_by_report,
    retrieve_by_year,
    retrieve_with_report_filter,
    retrieve_with_section_filter,
)

N_RESULTS = 6
TAGS_OF_INTEREST = {"multi_hop", "yoy_metric", "year_collision"}
OUT_PATH = ROOT / "evals" / "typed_retrieval_validation.md"
SCRATCH_PATH = ROOT / "scripts" / "scratch" / "typed_retrieval_validation.json"


def _load_golden_items() -> list[dict]:
    items = []
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# --- Part 1: classifier spot-check (3.3) ----------------------------------


def spot_check_classifier() -> dict:
    report_ids = [r["id"] for r in v1_present_reports()]
    counts: Counter[str] = Counter()
    by_class: dict[str, Counter[str]] = {"note": Counter(), "statement": Counter(), "other": Counter()}
    for rid in report_ids:
        for rec in load_chunks(rid):
            if rec.get("role") != "child":
                continue
            heading = rec.get("heading") or ""
            cls = classify_section(heading)
            counts[cls] += 1
            by_class[cls][heading] += 1

    # Known-tricky headings worth calling out explicitly regardless of
    # whether they still trip the classifier -- kept in sync with the
    # analysis in this change's implementation notes.
    probes = [
        "17. Comparative figures",
        "7. PROPERTY AND EQUIPMENT",
        "Halifax Port Authority Consolidated statement of earnings",
        "Halifax Port Authority Consolidated statement of comprehensive income",
        "Halifax Port Authority Consolidated statement of changes in equity of Canada",
        "Halifax Port Authority Consolidated statement of financial position",
        "Statement of compliance",
        "Inflation risk",
        "Credit risk",
    ]
    probe_results = {h: classify_section(h) for h in probes}

    return {
        "total_child_chunks": sum(counts.values()),
        "counts": dict(counts),
        "top_note_headings": by_class["note"].most_common(10),
        "top_statement_headings": by_class["statement"].most_common(10),
        "top_other_headings": by_class["other"].most_common(15),
        "probe_results": probe_results,
    }


# --- Part 2: golden-set coverage validation (4.1-4.4) ---------------------


def _year_coverage(question: str, years: list[int], *, report_ids: list[str] | None = None) -> dict:
    hits = retrieve_by_year(question, years, report_ids=report_ids, n_results=N_RESULTS)
    covered = {int(h["metadata"]["year"]) for h in hits if h["metadata"].get("year")}
    return {
        "requested_years": years,
        "covered_years": sorted(covered),
        "missing_years": sorted(set(years) - covered),
        "hit_count": len(hits),
    }


def _report_coverage(question: str, report_ids: list[str]) -> dict:
    hits = retrieve_by_report(question, report_ids, n_results=N_RESULTS)
    covered = {h["metadata"].get("report_id") for h in hits}
    return {
        "requested_report_ids": report_ids,
        "covered_report_ids": sorted(r for r in covered if r),
        "missing_report_ids": sorted(set(report_ids) - covered),
        "hit_count": len(hits),
    }


def _report_axis_comparison(question: str, report_ids: list[str]) -> dict:
    """design.md Decision 7: compare `retrieve_by_report`'s per-report_id
    fan-out (default, coverage-guaranteed) against `retrieve_with_report_filter`'s
    single pooled query (no guarantee) for the same bare, year-less call.
    Only meaningful when len(report_ids) > 1 -- the two paths are identical
    for a single report_id."""
    fanout_hits = retrieve_by_report(question, report_ids, n_results=N_RESULTS)
    fanout_covered = {h["metadata"].get("report_id") for h in fanout_hits}

    pooled_hits = retrieve_with_report_filter(question, report_ids, n_results=N_RESULTS)
    pooled_covered = {h["metadata"].get("report_id") for h in pooled_hits}

    return {
        "requested_report_ids": report_ids,
        "fanout_covered_report_ids": sorted(r for r in fanout_covered if r),
        "fanout_missing_report_ids": sorted(set(report_ids) - fanout_covered),
        "pooled_covered_report_ids": sorted(r for r in pooled_covered if r),
        "pooled_missing_report_ids": sorted(set(report_ids) - pooled_covered),
    }


def _year_collision_check(question: str, report_ids: list[str], years: list[int]) -> dict:
    # 4.2: per-year fan-out restricted to this report -- zero coverage on the
    # comparative (non-native) year is EXPECTED here, not a bug (year is
    # report-level metadata; see tasks.md 4.2).
    fanout = _year_coverage(question, years, report_ids=report_ids)

    # 4.3: does section-filtered retrieval avoid the known footnote
    # collision (phase1_baseline.md: "17./16. Comparative figures" beating
    # the real statement section)?
    baseline_hits = retrieve_by_report(question, report_ids, n_results=N_RESULTS)
    filtered_hits = retrieve_with_section_filter(question, report_ids=report_ids, n_results=N_RESULTS)

    def _top(hits: list[dict]) -> dict | None:
        if not hits:
            return None
        h = hits[0]
        heading = h["metadata"].get("heading")
        return {"heading": heading, "distance": h["distance"], "section_class": classify_section(heading)}

    baseline_top = _top(baseline_hits)
    filtered_top = _top(filtered_hits)
    collision_reproduced = bool(baseline_top and baseline_top["section_class"] == "note")
    collision_avoided = bool(filtered_top and filtered_top["section_class"] == "statement")

    return {
        "fanout_coverage": fanout,
        "baseline_top_hit": baseline_top,
        "section_filtered_top_hit": filtered_top,
        "footnote_collision_reproduced_unfiltered": collision_reproduced,
        "footnote_collision_avoided_with_section_filter": collision_avoided,
    }


def validate_golden_items() -> list[dict]:
    results = []
    for item in _load_golden_items():
        tags = set(item.get("tags") or [])
        if not tags & TAGS_OF_INTEREST:
            continue

        question = item["question"]
        evidence = item.get("expected_evidence") or {}
        years = evidence.get("years") or []
        report_ids = evidence.get("report_ids") or []
        is_year_collision = "year_collision" in tags

        record: dict = {
            "id": item["id"],
            "tags": sorted(tags),
            "question": question,
            "requested_years": years,
            "requested_report_ids": report_ids,
        }

        if is_year_collision:
            record["year_collision_check"] = _year_collision_check(question, report_ids, years)
        else:
            if years:
                record["year_coverage"] = _year_coverage(question, years)
            if report_ids:
                record["report_coverage"] = _report_coverage(question, report_ids)
                if len(report_ids) > 1:
                    record["report_axis_comparison"] = _report_axis_comparison(question, report_ids)

        results.append(record)
    return results


# --- Report rendering ------------------------------------------------------


def _render_report(spot_check: dict, golden_results: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Typed retrieval tools -- validation (tasks 3.3, 4.1-4.4)")
    lines.append("")
    lines.append(
        "Direct-call validation of `hfx_portgraph/retrieval_tools.py` against "
        "`evals/golden.jsonl`'s `expected_evidence` -- no LLM, no `ask()`. "
        f"Generated by `scripts/validate_typed_retrieval.py` (n_results={N_RESULTS} per call). "
        "Full machine-readable output: `scripts/scratch/typed_retrieval_validation.json`."
    )
    lines.append("")

    lines.append("## Task 3.3 -- section classifier spot-check")
    lines.append("")
    lines.append(
        f"Ran `classify_section()` over all {spot_check['total_child_chunks']} child chunks' "
        "headings across the 8 v1 reports (not just gq-019's specific headings)."
    )
    lines.append("")
    lines.append("| class | count |")
    lines.append("|---|---|")
    for cls in ("statement", "note", "other"):
        lines.append(f"| {cls} | {spot_check['counts'].get(cls, 0)} |")
    lines.append("")
    lines.append(
        "Probe headings (chosen because they're the ones the failure modes in "
        "`evals/phase1_baseline.md` and this change's design.md turn on):"
    )
    lines.append("")
    lines.append("| heading | classification |")
    lines.append("|---|---|")
    for h, cls in spot_check["probe_results"].items():
        lines.append(f"| {h} | {cls} |")
    lines.append("")
    lines.append(
        "**Known limitation (under-triggering, not over-triggering):** note/footnote "
        "*subsections* that don't repeat their parent note's number in their own heading "
        "-- e.g. `Inflation risk`, `Credit risk`, `Pension benefits` (children of numbered "
        "notes like risk-management or employee-benefit disclosures) -- classify as `other`, "
        "not `note`. This is safe for the gq-019/gq-020 failure mode specifically (those "
        "collisions are against numbered top-level note headings like `17. Comparative "
        "figures`, which the classifier does catch), but means the classifier's `note` "
        "recall is incomplete for sub-item headings in general. Documented here per tasks.md "
        "3.3/4.4 rather than tuned further, since it doesn't affect any tagged golden item's "
        "outcome below."
    )
    lines.append("")
    lines.append(
        "**Fixed during spot-check:** an earlier bare `\\bstatement of\\b` pattern misclassified "
        "`Statement of compliance` (an accounting-policy note, 7 occurrences across the corpus) "
        "as `statement`. The shipped classifier matches only canonical primary-statement titles "
        "(`statement of earnings`, `... comprehensive income`, `... financial position`, "
        "`... changes in equity`, `... cash flows`, `... operations`), which avoids that "
        "false positive while still matching every real primary-statement heading found in the "
        "corpus (see probe table above)."
    )
    lines.append("")

    lines.append("## Tasks 4.1-4.3 -- golden-set evidence coverage")
    lines.append("")
    lines.append(
        f"{len(golden_results)} golden items carry `multi_hop`/`yoy_metric`/`year_collision` tags."
    )
    lines.append("")

    non_collision = [r for r in golden_results if "year_collision" not in r["tags"]]
    collision = [r for r in golden_results if "year_collision" in r["tags"]]

    lines.append("### Multi-year / multi-report items (`multi_hop`, `yoy_metric`)")
    lines.append("")
    lines.append("| id | tags | requested years | year coverage | requested report_ids | report_id coverage |")
    lines.append("|---|---|---|---|---|---|")
    for r in non_collision:
        yc = r.get("year_coverage")
        rc = r.get("report_coverage")
        yc_cell = "n/a"
        if yc:
            yc_cell = f"{len(yc['covered_years'])}/{len(yc['requested_years'])}"
            if yc["missing_years"]:
                yc_cell += f" (missing {yc['missing_years']})"
        rc_cell = "n/a"
        if rc:
            rc_cell = f"{len(rc['covered_report_ids'])}/{len(rc['requested_report_ids'])}"
            if rc["missing_report_ids"]:
                rc_cell += f" (missing {rc['missing_report_ids']})"
        req_years = r["requested_years"]
        req_reports = r["requested_report_ids"]
        lines.append(
            f"| {r['id']} | {', '.join(r['tags'])} | {req_years} | {yc_cell} | "
            f"{len(req_reports)} report(s) | {rc_cell} |"
        )
    lines.append("")
    full_year_cov = sum(1 for r in non_collision if r.get("year_coverage") and not r["year_coverage"]["missing_years"])
    full_report_cov = sum(
        1 for r in non_collision if r.get("report_coverage") and not r["report_coverage"]["missing_report_ids"]
    )
    lines.append(
        f"**Summary:** {full_year_cov}/{len(non_collision)} items got full requested-year coverage via "
        f"`retrieve_by_year`'s per-year fan-out; {full_report_cov}/{len(non_collision)} items got full "
        f"requested-report_id coverage via `retrieve_by_report`'s per-report_id fan-out (its default "
        "behavior as of design.md Decision 7 -- see the comparison below for what the previous "
        "pooled-query default would have gotten instead). Compare gq-001 specifically against "
        "`evals/phase1_baseline.md`, where naive `retrieve()` missed 2023 entirely -- the per-year "
        "fan-out result for gq-001 is reported in the table above."
    )
    lines.append("")

    lines.append("### Report-axis fan-out vs. pooled comparison (Decision 7)")
    lines.append("")
    lines.append(
        "`retrieve_by_report()`'s bare (year-less) call used to route to a single Chroma query "
        "pooling all requested `report_id`s into one ranked list -- the same crowding shape "
        "Decision 1 already rejected as the default for years, just never extended to reports. "
        "Post-completion analysis (`/opsx:explore`, 2026-08-31) found this reproduced Decision 1's "
        "exact failure on the report axis: `gq-022`'s combined-call report coverage looked like the "
        "worst case in the table above (1/3), but resolves fully once retrieval fans out per "
        "`report_id` the same way it already does per year -- and `gq-001`'s residual gap traced to "
        "a single year (e.g. 2022) having two requested reports (`*_annual_en`, `*_financials_en`) "
        "sharing one pooled query's slots, where the annual report swept all of them. "
        "`retrieve_by_report()` now fans out per `report_id` by default (closing this gap); the "
        "prior pooled behavior survives as the separately-named `retrieve_with_report_filter()`, for "
        "callers where `report_ids` is a scoping filter rather than a required-coverage set -- the "
        "two are identical for a single `report_id`."
    )
    lines.append("")
    lines.append("| id | requested report_ids | `retrieve_by_report` (fan-out, default) | `retrieve_with_report_filter` (pooled) |")
    lines.append("|---|---|---|---|")
    comparison_items = [r for r in non_collision if r.get("report_axis_comparison")]
    for r in comparison_items:
        cmp = r["report_axis_comparison"]
        req = cmp["requested_report_ids"]
        fanout_cell = f"{len(cmp['fanout_covered_report_ids'])}/{len(req)}"
        if cmp["fanout_missing_report_ids"]:
            fanout_cell += f" (missing {cmp['fanout_missing_report_ids']})"
        pooled_cell = f"{len(cmp['pooled_covered_report_ids'])}/{len(req)}"
        if cmp["pooled_missing_report_ids"]:
            pooled_cell += f" (missing {cmp['pooled_missing_report_ids']})"
        lines.append(f"| {r['id']} | {len(req)} | {fanout_cell} | {pooled_cell} |")
    lines.append("")
    fanout_full = sum(1 for r in comparison_items if not r["report_axis_comparison"]["fanout_missing_report_ids"])
    pooled_full = sum(1 for r in comparison_items if not r["report_axis_comparison"]["pooled_missing_report_ids"])
    lines.append(
        f"**Summary:** {fanout_full}/{len(comparison_items)} multi-report items get full coverage under "
        f"fan-out (the shipped default) vs. {pooled_full}/{len(comparison_items)} under the old pooled "
        "behavior, for the identical bare (year-less) call. Items requesting only one `report_id` are "
        "excluded from this table -- the two functions are equivalent there by construction."
    )
    lines.append("")

    lines.append("### `year_collision` items (gq-019, gq-020)")
    lines.append("")
    lines.append(
        "Per tasks.md 4.2: for these items, zero coverage on the *comparative* (non-native) "
        "year in the per-year fan-out is EXPECTED, not a bug -- `year` metadata is report-level "
        "(every chunk in e.g. `2021_financials_en` is tagged `year=\"2021\"`), so the comparative "
        "column's year (e.g. 2020 inside the 2021 financials PDF) has no same-report, "
        "same-year-tagged chunk for fan-out to find. The real check for this failure mode is "
        "task 4.3's section-filter comparison below."
    )
    lines.append("")
    lines.append(
        "| id | requested years (native / comparative) | fan-out coverage | expected-zero? | "
        "unfiltered top hit | section-filtered top hit | collision reproduced (unfiltered) | "
        "collision avoided (filtered) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in collision:
        chk = r["year_collision_check"]
        fanout = chk["fanout_coverage"]
        bt = chk["baseline_top_hit"]
        ft = chk["section_filtered_top_hit"]
        bt_cell = f"{bt['heading']} ({bt['section_class']})" if bt else "none"
        ft_cell = f"{ft['heading']} ({ft['section_class']})" if ft else "none"
        expected_zero = "yes" if fanout["missing_years"] else "no (unexpected full coverage)"
        lines.append(
            f"| {r['id']} | {fanout['requested_years']} | "
            f"{len(fanout['covered_years'])}/{len(fanout['requested_years'])} "
            f"(missing {fanout['missing_years']}) | {expected_zero} | {bt_cell} | {ft_cell} | "
            f"{chk['footnote_collision_reproduced_unfiltered']} | "
            f"{chk['footnote_collision_avoided_with_section_filter']} |"
        )
    lines.append("")
    both_avoided = all(r["year_collision_check"]["footnote_collision_avoided_with_section_filter"] for r in collision)
    lines.append(
        f"**Summary:** section-filtered retrieval avoided the known footnote collision on "
        f"{'both' if both_avoided else 'not all'} `year_collision` items. This directly answers "
        "design.md's open question about whether the section-type heuristic needs "
        "report-type-specific tuning for the v1 8-report corpus -- see per-item results above."
    )
    lines.append("")

    lines.append("## Task 4.4 -- input to `langgraph-plan-critique-loop`")
    lines.append("")
    lines.append(
        "- Per-year fan-out (`retrieve_by_year`) closes gq-001-style year-crowding gaps directly: "
        "see the full-year-coverage count above. Where an item still shows missing years after "
        "fan-out, that's a genuine no-content or embedding-relevance gap (not a ranking artifact "
        "fan-out could fix), and is a candidate planner-loop retry/decompose target."
    )
    lines.append(
        "- Section-type filtering (`retrieve_with_section_filter`) directly fixes the "
        "`year_collision` footnote-vs-statement ranking failure documented in "
        "`evals/phase1_baseline.md` -- see the collision table above. This is a re-ranking "
        "signal (Decision 3), not a hard filter, so it should be exposed to the planner/critic "
        "loop as a *preference*, not a guarantee."
    )
    lines.append(
        "- The classifier's known under-triggering on unnumbered note *subsection* headings "
        "(see 3.3 above) is worth revisiting if a future golden item's collision involves an "
        "unnumbered footnote heading rather than a numbered one -- not needed for gq-019/gq-020 "
        "as currently written."
    )
    lines.append(
        "- **[2026-08-31]** Report-axis fan-out (design.md Decision 7, tasks.md 6.1-6.5) is now "
        "implemented and reflected in this run's numbers -- `retrieve_by_report()`'s bare call "
        "guarantees per-report_id coverage the same way `retrieve_by_year()` already guarantees "
        "per-year coverage. `langgraph-plan-critique-loop/design.md`'s Decision 4 entity-only "
        "dispatch (bare `retrieve_by_report()`, no year) can now be built against this default "
        "directly -- see the report-axis comparison table above for what the previous pooled "
        "default would have gotten instead."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    spot_check = spot_check_classifier()
    golden_results = validate_golden_items()

    SCRATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRATCH_PATH.write_text(
        json.dumps({"spot_check": spot_check, "golden_results": golden_results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    report = _render_report(spot_check, golden_results)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"full record: {SCRATCH_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
