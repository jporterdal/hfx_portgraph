## 1. Persist full provenance from parse

- [x] 1.1 In `parse_report()`, write `corpus/parsed/{report_id}/provenance.json` containing the full `_collect_provenance()` output (document order, all items), alongside the existing `document.md`/`meta.json`/`tables.md` outputs
- [x] 1.2 Keep `meta.json`'s `provenance_sample`/`provenance_item_count` as a small human-scannable summary; do not inline the full list there
- [x] 1.3 Update `parse_report()`'s idempotency check (`md_path.exists() and meta_path.exists()`) to also require `provenance.json` to exist, so already-parsed v1 reports get the new sidecar written on next non-`--force` run instead of silently staying without one
- [x] 1.4 Re-run parse (non-force, relying on 1.3) for all 8 v1 `annual`/`financials` reports and confirm `provenance.json` now exists for each with a row count matching `meta.json`'s `provenance_item_count`

## 2. Resolve parent (section) page ranges

- [x] 2.1 Add a helper that filters a loaded provenance list to `section_header`-labeled rows, in document order
- [x] 2.2 In `chunk_report()`, zip that filtered list positionally against `_parse_sections()`'s headings (in the same document order) to assign each section a page range
- [x] 2.3 Implement the divergence rule: once heading count and `section_header` anchor count diverge, stop pairing — sections from that point on are left unresolved (`page_start`/`page_end` = `None`) rather than mis-paired
- [x] 2.4 Set parent chunk records' `page_start`, `page_end` (min/max of the matched row's pages) and `page_source = "matched"` when resolved

## 3. Resolve child (passage) page ranges

- [x] 3.1 Add a helper that filters a section's provenance rows to non-heading, non-picture labels (`text`, `list_item`), in document order, scoped to that section
- [x] 3.2 Track, as `_split_paragraphs()`/`_pack_children()` pack paragraphs into each child, which provenance rows' text fed that child (positional walk within the section, mirroring task 2's approach)
- [x] 3.3 Set each child's `page_start`/`page_end` to the min/max pages across its matched rows and `page_source = "matched"` when resolved
- [x] 3.4 When a child's paragraphs don't resolve via 3.2/3.3 but its parent section resolved in task 2, set the child's `page_start`/`page_end` to the parent's range and `page_source = "inherited"`
- [x] 3.5 When neither resolves, leave the child's `page_start`/`page_end` as `None` (no `page_source`), consistent with the existing section-heading citation fallback in `rag.py`

## 4. Clean up superseded code

- [x] 4.1 Remove `heading_page_map()` from `parse.py` (unused; superseded by tasks 2–3's positional matching embedded in `chunk_report()`)
- [x] 4.2 Confirm no remaining references to `heading_page_map` anywhere in the codebase

## 5. Regenerate artifacts and verify

- [x] 5.1 Re-run `chunk_report(force=True)` for all 8 v1 `annual`/`financials` reports
- [x] 5.2 Verify `chunk_id` and `text` fields are byte-identical to the pre-change chunk files for all 8 reports (only the page/`page_source` fields should differ) — guards against Chroma ID orphaning (see note below: `chunk_id` fully stable; `text` byte-identical for 6/8 reports, with 2 tiny non-deterministic-OCR diffs in the other 2 — see summary)
- [x] 5.3 Spot-check resolved `page_start`/`page_end` against the real source PDFs for a sample of parent and child chunks across at least 2 reports (prefer `2023_annual_en`, given its known figure-heavy pages, and one `financials` report)
- [x] 5.4 Measure how many sections/children land on `"matched"` vs `"inherited"` vs unresolved across the 8-report v1 corpus; note the result in this change's design.md Open Questions or a follow-up note
- [x] 5.5 Re-run `index_corpus.py --v1-batch --reset` to rebuild `data/chroma/` from the regenerated chunks
- [x] 5.6 Re-run the `evals/phase1_baseline.md` smoke items (at minimum `gq-005`) via `ask.py` and confirm citations now include a real page number instead of `"unknown"`

## 6. Documentation

- [x] 6.1 Add a follow-up note to `evals/phase1_baseline.md` marking the "Page-level citation is not yet real" observation as resolved, with a pointer to this change
- [x] 6.2 Note in `docs/phase-1.md`'s parse/chunk step descriptions that page provenance is now resolved (matched/inherited) rather than absent
