## 1. Report-type helper (foundation)

- [x] 1.1 Add a helper that resolves `report_type` for a given `report_id` (or list of ids) from `corpus/manifest.yaml`, raising a clear error for any id not present in the manifest
- [x] 1.2 Add a helper that expands a `report_type` (annual/financials) into the matching `report_id` list via the manifest, for callers that want to filter by type rather than explicit ids

## 2. Year- and report-scoped retrieval

- [x] 2.1 Implement `retrieve_by_year(years, ...)`: embed the query once, fan out one Chroma query per requested year using `where={"year": {"$eq": str(y)}}` — Chroma metadata stores `year` as a string (`rag.py::index_reports`), so callers' int years MUST be cast to `str()` before building the filter or the `$eq` match silently returns zero hits — and merge results so every year with matching content contributes at least one hit
- [x] 2.2 Implement `retrieve_by_report(report_ids, ...)`: single Chroma query with `where={"report_id": {"$in": report_ids}}`. **[2026-08-31]** This single-query shape is superseded as the *default* by `design.md`'s Decision 7 amendment (fan-out per `report_id`, matching 2.1's year fan-out; this shape survives as the separately-named `retrieve_with_report_filter`) — decided, not yet implemented; see Decision 7 for the finding and status.
- [x] 2.3 Support combining year + report_id constraints in one call (both `where` clauses applied together, years cast to `str()` per 2.1) for callers that need both
- [x] 2.4 Ensure all new functions return hits in the exact shape `retrieve()` already returns (`chunk_id`, `text`, `distance`, `metadata`, `parent_text`), reusing `retrieve()`'s parent-text lookup logic rather than duplicating it

## 3. Section-type-aware retrieval

- [x] 3.1 Write a heuristic classifier over `heading`/`section` text distinguishing note/footnote-like headings (e.g. leading numbered pattern) from primary-statement-like headings (e.g. "Statement of" / "Consolidated statement of" keyword pattern)
- [x] 3.2 Implement `retrieve_with_section_filter(...)`: run the underlying query, classify each hit's section, and re-rank so primary-statement-labeled hits are preferred over note/footnote-labeled hits when both are present for the same query
- [x] 3.3 Spot-check the classifier against real headings from the 8 v1 reports' parsed sections (not just gq-019's specific case) to catch obvious over/under-triggering before validation

## 4. Golden-set validation

- [x] 4.1 Write a validation script that, for every `multi_hop`/`yoy_metric`/`year_collision`-tagged item in `evals/golden.jsonl`, calls the typed functions directly (no LLM, no `ask()`) using each item's `expected_evidence.years`/`report_ids`
- [x] 4.2 For each item, record whether returned hits cover every requested year (or report id) with available indexed content. For `year_collision` items (gq-019, gq-020), zero coverage on one of the two requested years is the EXPECTED result of the per-year fan-out check, not a bug: `year` metadata is report-level (every chunk in `2021_financials_en` is tagged `year="2021"`, per `chunk.py::chunk_report`), so the comparative-column year (e.g. 2020 inside the 2021 financials PDF) never has a same-report, same-year-tagged chunk for fan-out to find. Annotate these two items' 4.2 results as expected-zero and point to 4.3, which is the actual coverage check for this failure mode
- [x] 4.3 For the `year_collision`-tagged items (gq-019, gq-020), record whether section-filtered retrieval avoids the known footnote-collision failure documented in `evals/phase1_baseline.md`
- [x] 4.4 Write results to `evals/typed_retrieval_validation.md`, including any classifier misses or coverage gaps found in 4.1–4.3, framed as input to the upcoming `langgraph-plan-critique-loop` design

## 5. Wrap-up

- [x] 5.1 Confirm no changes were made to `corpus/parsed/`, `corpus/chunks/`, `data/chroma/` artifacts, `ask()`, or `cli.py` (this change is additive only)
- [x] 5.2 Add a short pointer note in `evals/phase1_baseline.md` referencing `evals/typed_retrieval_validation.md` for readers following the gq-001/gq-019 threads forward

## 6. Report-axis fan-out (Decision 7 follow-up, added 2026-08-31)

This change was previously complete (15/15). Post-completion `/opsx:explore` analysis found `retrieve_by_report()`'s bare (year-less) call path reproduces Decision 1's exact per-key crowding failure on the `report_id` axis — see `design.md` Decision 7 and `evals/typed_retrieval_validation.md`'s 2026-08-31 addendum for the empirical justification. These tasks implement the decided fix.

- [x] 6.1 Change `retrieve_by_report()`'s year-less path to fan out one Chroma query per requested `report_id` (`where={"report_id": {"$eq": rid}}`), mirroring `retrieve_by_year`'s loop exactly — embed once, merge/dedupe, guaranteeing ≥1 hit per requested `report_id` with matching content. The `years`-given path keeps delegating into `retrieve_by_year` unchanged (2.3).
- [x] 6.2 Add `retrieve_with_report_filter(question, report_ids, ...)` preserving the prior single-`$in`-query pooled behavior (no coverage guarantee), named to parallel `retrieve_with_section_filter`'s existing "pooled query, no hard guarantee" naming convention.
- [x] 6.3 Extend `scripts/validate_typed_retrieval.py` to compute the `retrieve_by_report` (fan-out) vs. `retrieve_with_report_filter` (pooled) comparison automatically per multi-report golden item, replacing the addendum's hand-derived three-way table with a script-generated two-column one (bare and flat-fan-out collapse to the same call once 6.1 ships).
- [x] 6.4 Re-run the script; regenerate `evals/typed_retrieval_validation.md` in full (main table's report-coverage numbers now reflect the fan-out default; addendum section replaced by the script-generated comparison) rather than hand-editing stale numbers. Result: 10/10 items now get full report-id coverage (up from 7/10); the new comparison table shows 9/9 full coverage under fan-out vs. 6/9 under the old pooled default.
- [x] 6.5 Update `design.md` Decision 7's status line and the Open Questions ownership bullet from "decided, not implemented" to implemented, and update `langgraph-plan-critique-loop`'s cross-referencing notes (design.md Decision 4, tasks.md 3.1, proposal.md dependency line) to reflect that the dependency is now satisfied.
