## Why

Investigating a retrieval-ranking question on `gq-012` (documented in `evals/phase1_baseline.md`'s
2026-08-24 addendum) surfaced a corpus-quality problem upstream of embeddings or retrieval: PDF
page furniture — running headers, footers, and letterhead reprinted on every page — is not being
separated from real content during parsing, and this is actively corrupting chunk structure, not
just adding cosmetic noise.

Two effects were found and quantified against the live v1 corpus (8 reports, 1147 child chunks):

1. **Furniture text is misclassified as document structure.** `HALIFAX PORT AUTHORITY - NOTES TO
   THE CONSOLIDATED FINANCIAL STATEMENTS` (or the equivalent per-report running header) is printed
   on every page of each report's financial-notes section. Docling exports it as a markdown `##`
   heading, and `chunk.py::_parse_sections()` treats every occurrence as a new section boundary.
   In `2020_annual_en`, this single repeated line accounts for 23 of the document's 221 total
   section headings (10%) — and it fragments real multi-page notes into disconnected pieces. Note
   7 ("PROPERTY AND EQUIPMENT"), a single logical note spanning 3 pages, is split into 5 separate
   parent sections by this mechanism alone, each inheriting the running header's text as its
   `heading`/`section` metadata instead of the note's real topic. The same pattern (a repeated
   `## Halifax Port Authority Notes to the consolidated financial statements` heading, 20-26
   occurrences) was confirmed present in all 8 reports' parsed markdown.

2. **Furniture text pollutes otherwise-legitimate chunk content.** Address blocks, phone/fax
   numbers, ISO certification numbers, and repeated running-header/footer text end up embedded
   inline inside child chunks. A frequency scan (lines repeating ≥3 times verbatim within a
   report's parsed markdown, digit-normalized) found 170 of 1147 child chunks (14.8%) contain at
   least one such line, ranging from 5.8% (`2022_annual_en`) to 19.0% (`2022_financials_en`,
   `2023_financials_en`). This is milder per-chunk (0.3-1.3% of characters in affected chunks) but
   widespread.

Docling was checked directly for a built-in fix and does not provide one for this corpus: Docling
has first-class concepts for exactly this distinction (`DocItemLabel.PAGE_HEADER`/`PAGE_FOOTER`,
and a separate `ContentLayer.FURNITURE` vs `BODY` split, with `export_to_markdown()` able to filter
on either), but re-running the converter on `2020_annual_en.pdf` and inspecting the resulting
`DoclingDocument` directly showed **100% of items classified as `ContentLayer.BODY`** (zero
`FURNITURE`), and the repeated running header specifically labeled `section_header`, not
`page_header`. Docling's layout model is not detecting this document's running headers as
furniture, so there is no free metadata this project can filter on — any mitigation has to be a
heuristic added to this project's own parse/chunk pipeline.

This corpus-quality gap sits directly under the report sections (financial notes) that most
numeric/financial golden questions target, and is a plausible contributor to previously observed
retrieval oddities (e.g. the `year_collision` failure mode noted for `gq-019` in
`evals/phase1_baseline.md`, and the boilerplate-heavy chunk that ranked #2 for `gq-012`).

## What Changes

This proposal originally documented the problem and candidate mitigation options without committing
to one. A follow-up design pass (see `design.md`'s Decisions section) has since selected and scoped
an approach — a synthesis of the bbox-position and text-repetition options, fused with Docling's own
furniture flag — and `tasks.md` now carries the implementation checklist. The two problems remain
distinct and are addressed by two separate mechanisms, not one:

- **Furniture-as-heading** (structural, higher severity): repeated running-header text rendered as
  a markdown heading fragments real multi-page sections into disconnected parent chunks. Addressed
  by `design.md` Decision 3 — a two-pass, registry-based fold in `chunk.py`, scoped to
  `section_header`-labeled items and text-repetition only (no bbox signal needed).
- **Furniture-in-content** (cosmetic, lower severity, more widespread): repeated footer/address/
  masthead boilerplate embedded inline within otherwise-legitimate child chunk text, and more
  generally any page header/footer chrome. Addressed by `design.md` Decision 1 — a fused signal
  (bbox position-consistency + fuzzy text-repetition + Docling's `FURNITURE` flag, combined 2-of-3
  with a Docling+text fast-track) computed in `parse.py`, which now strips qualifying furniture
  before `document.md` is written rather than leaving it for `chunk.py` to filter after the fact.

A learned classifier over the same three signals was considered as an alternative to hand-writing
the fusion rule (see `design.md`'s "Rejected alternative") and deferred — no labeled ground truth
exists yet to train or evaluate one against, so it would only restate the rule below in soft-weighted
form. Worth revisiting once the rule-based signal's real-world precision/recall is measurable.

## Capabilities

### Modified Capabilities

- `document-parse`: "Preserve citation provenance" — heading identifiers exported into parsed
  Markdown are not currently guaranteed to reflect real document structure; text that is page
  furniture (reprinted verbatim across many pages) can be exported as if it were a genuine section
  heading.
- `parent-child-chunking`: "Hierarchical parent chunks" and "Child passage chunks" — parent
  boundaries currently trust raw markdown heading structure without accounting for repeated
  furniture headings (which can fragment one logical section into many small parents), and child
  chunk text is not currently guaranteed to exclude repeated page-furniture artifacts.

## Impact

- **Code:** `hfx_portgraph/parse.py` (`_collect_provenance`, `_export_markdown`, `parse_report`) gains
  the fused furniture-detection signal, full-content-layer item capture, and an `items.jsonl` audit
  sidecar. `hfx_portgraph/chunk.py` (`_parse_sections`, `chunk_report`) gains the two-pass
  running-header/subtext registry. See `tasks.md`.
- **Data:** `corpus/parsed/*/document.md` (furniture-stripped) and `corpus/chunks/*.jsonl`
  (fewer, less-fragmented parents; furniture-free child text) for all 8 v1 reports, plus new
  `corpus/parsed/*/items.jsonl` audit sidecars — re-parsing and re-chunking all 8 reports is part of
  `tasks.md`, not deferred to a follow-up.
- **Downstream:** `data/chroma` reindexing and an `evals/phase1_baseline.md` addendum re-running the
  golden subset (especially `gq-012`, `gq-019`) against the corrected corpus are both included in
  `tasks.md`, following the same "numbers moved, here's why" pattern the `nomic-embed-task-prefixes`
  change already went through.
- **Specs:** `document-parse` and `parent-child-chunking` delta specs updated to reflect the fused
  signal and the running-subtext mechanism (not just running headers) — see `specs/`.
