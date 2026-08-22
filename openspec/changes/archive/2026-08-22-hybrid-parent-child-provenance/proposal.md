## Why

`chunk.py` hardcodes `page_start`/`page_end` to `None` on every chunk record, even though `parse.py` already computes full page-level provenance via `_collect_provenance()` — it's just discarded after a 50-item preview is written to `meta.json`. `rag.py` is already fully wired to consume real page numbers (Chroma metadata, citation prompt template, returned citations), so this single gap silently degrades every citation in the system to "page unknown." It's a known, previously-accepted Phase 1 gap (flagged in `design.md`'s risk table and confirmed in `evals/phase1_baseline.md`), but Phase 2 and Phase 3 build directly on top of the current parse/chunk substrate rather than replacing it — so whatever citation quality exists here becomes the ceiling for every later phase, including Phase 3's Neo4j fact provenance and Phase 4's report "source trail." Fixing it now, before Phase 3 ingests facts against the current section-only citation shape, is materially cheaper than retrofitting it later.

## What Changes

- `parse_report()` persists the full provenance list (currently computed then discarded) as a new sidecar `corpus/parsed/{report_id}/provenance.json`, since `parse` and `chunk` run as separate CLI processes and nothing in-memory survives between them.
- `chunk_report()` resolves **parent** (section) `page_start`/`page_end` by walking `section_header`-labeled provenance rows in document order and pairing them **positionally** against the H2/H3 headings from `_parse_sections()` — replacing the exact-text-equality matching in the existing (currently unused) `heading_page_map()`, which collides when heading text repeats (e.g. adjacent single-word headings from a wrapped title).
- `chunk_report()` resolves **child** (passage) `page_start`/`page_end` more precisely by walking each section's non-heading provenance rows (`text`/`list_item`) against the paragraphs packed into that child, taking the min/max page across the rows that fed it.
- A fallback chain replaces the current all-or-nothing `None`: child-level exact match → inherit parent's resolved range → leave unresolved (section-heading citation remains the terminal fallback, matching `design.md`'s already-approved mitigation).
- A new `page_source` field (`"matched"` | `"inherited"`) is added to parent and child chunk records so downstream consumers — Phase 3 Neo4j extraction in particular — can distinguish confidently-matched pages from coarser inherited ones before treating a fact as citable.
- The existing `heading_page_map()` function in `parse.py` is removed and superseded by the positional-matching logic embedded in `chunk_report()` (it was never called from anywhere in the codebase).
- No changes to `rag.py` — it already reads `page_start`/`page_end` from chunk metadata and treats missing values as `"unknown"` gracefully; citations light up automatically once `chunk.py` stops writing `None`.
- Existing chunk artifacts for the 8 v1 `annual`/`financials` reports are regenerated (`chunk_report(force=True)`) and spot-checked against real PDFs and against `evals/phase1_baseline.md`'s previously observed citations (e.g. `gq-005`).

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `document-parse`: parse output now persists the full page/heading provenance list (not just a 50-item sample) as a durable sidecar artifact, strengthening the existing "Preserve citation provenance" requirement.
- `parent-child-chunking`: child (and parent) chunk records now resolve real `page_start`/`page_end` values via positional provenance matching with a defined fallback chain, and carry a new `page_source` field — making "page range" the real default outcome of the existing "page range or section provenance" requirement rather than a permanently-unmet branch.

## Impact

- **Code**: `hfx_portgraph/parse.py` (`_collect_provenance`, `parse_report`, removal of `heading_page_map`), `hfx_portgraph/chunk.py` (`chunk_report`, new positional-matching helpers).
- **New artifact**: `corpus/parsed/{report_id}/provenance.json` sidecar per report (8 v1 reports today).
- **Regenerated artifacts**: `corpus/chunks/{report_id}.jsonl` for all 8 v1 `annual`/`financials` reports must be rebuilt from the updated parse outputs.
- **Downstream**: `data/chroma/` index should be re-built (`index_corpus.py --v1-batch --reset`) so served citations reflect the new page data; no code changes required in `rag.py` or `cli.py`.
- **No impact** to the in-progress `visual-kpi-vlm-extraction` change — its `kpi_facts.jsonl` provenance comes directly from VLM crop extraction, independent of this path.
- **Docs**: `evals/phase1_baseline.md`'s "Page-level citation is not yet real" observation becomes stale and should get a follow-up note once this lands; `openspec/specs/parent-child-chunking/spec.md` wording should be tightened to reflect page range as the real default.
