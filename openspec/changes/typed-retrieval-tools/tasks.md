## 1. Report-type helper (foundation)

- [ ] 1.1 Add a helper that resolves `report_type` for a given `report_id` (or list of ids) from `corpus/manifest.yaml`, raising a clear error for any id not present in the manifest
- [ ] 1.2 Add a helper that expands a `report_type` (annual/financials) into the matching `report_id` list via the manifest, for callers that want to filter by type rather than explicit ids

## 2. Year- and report-scoped retrieval

- [ ] 2.1 Implement `retrieve_by_year(years, ...)`: embed the query once, fan out one Chroma query per requested year using `where={"year": {"$eq": y}}`, and merge results so every year with matching content contributes at least one hit
- [ ] 2.2 Implement `retrieve_by_report(report_ids, ...)`: single Chroma query with `where={"report_id": {"$in": report_ids}}`
- [ ] 2.3 Support combining year + report_id constraints in one call (both `where` clauses applied together) for callers that need both
- [ ] 2.4 Ensure all new functions return hits in the exact shape `retrieve()` already returns (`chunk_id`, `text`, `distance`, `metadata`, `parent_text`), reusing `retrieve()`'s parent-text lookup logic rather than duplicating it

## 3. Section-type-aware retrieval

- [ ] 3.1 Write a heuristic classifier over `heading`/`section` text distinguishing note/footnote-like headings (e.g. leading numbered pattern) from primary-statement-like headings (e.g. "Statement of" / "Consolidated statement of" keyword pattern)
- [ ] 3.2 Implement `retrieve_with_section_filter(...)`: run the underlying query, classify each hit's section, and re-rank so primary-statement-labeled hits are preferred over note/footnote-labeled hits when both are present for the same query
- [ ] 3.3 Spot-check the classifier against real headings from the 8 v1 reports' parsed sections (not just gq-019's specific case) to catch obvious over/under-triggering before validation

## 4. Golden-set validation

- [ ] 4.1 Write a validation script that, for every `multi_hop`/`yoy_metric`/`year_collision`-tagged item in `evals/golden.jsonl`, calls the typed functions directly (no LLM, no `ask()`) using each item's `expected_evidence.years`/`report_ids`
- [ ] 4.2 For each item, record whether returned hits cover every requested year (or report id) with available indexed content
- [ ] 4.3 For the `year_collision`-tagged items (gq-019, gq-020), record whether section-filtered retrieval avoids the known footnote-collision failure documented in `evals/phase1_baseline.md`
- [ ] 4.4 Write results to `evals/typed_retrieval_validation.md`, including any classifier misses or coverage gaps found in 4.1–4.3, framed as input to the upcoming `langgraph-plan-critique-loop` design

## 5. Wrap-up

- [ ] 5.1 Confirm no changes were made to `corpus/parsed/`, `corpus/chunks/`, `data/chroma/` artifacts, `ask()`, or `cli.py` (this change is additive only)
- [ ] 5.2 Add a short pointer note in `evals/phase1_baseline.md` referencing `evals/typed_retrieval_validation.md` for readers following the gq-001/gq-019 threads forward
