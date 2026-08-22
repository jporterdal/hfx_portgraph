## Context

`hfx_portgraph/parse.py`'s `_collect_provenance()` already walks Docling's `document.iterate_items()` and captures, for every item, its label (`section_header`, `text`, `list_item`, `picture`, ...), a 240-char text preview, and its page number(s) — in document order. `parse_report()` computes this full list, then throws it away: only `provenance[:50]` survives, written into `meta.json` as a debug sample. `chunk_report()` (in `hfx_portgraph/chunk.py`) never reads it and hardcodes `page_start`/`page_end` to `None` on every parent and child record.

`parse` and `chunk` run as separate CLI subcommands (`cli.py:39`, `cli.py:50`), so nothing in-memory survives between them — any fix has to persist provenance to disk.

`rag.py` is already fully built to consume real page numbers: it embeds `page_start`/`page_end` into Chroma metadata, formats citation strings (`page_start={...}`), and forces the LLM to cite in that shape. It degrades gracefully on `None` today (`page_start or 'unknown'`), so no changes are needed there — this change only has to stop feeding it nulls.

An existing, unused helper `heading_page_map()` was written for exactly this purpose but never wired in. It matches by exact string equality between a markdown heading line and a provenance row's `text_preview`. Spot-checking real parsed output (`corpus/parsed/2023_annual_en/`) confirms this works for a well-formed heading, but the same sample also shows adjacent single-word headings (`## PORT` / `## PERFORMANCE`) from what was one wrapped title in the source PDF — a case where duplicate/short heading text would collide in a text-keyed dict, silently overwriting an earlier section's page.

This gap is known and was previously accepted: `design.md` (archived, phase-1-parse-rag) named it as a risk with "store section headings as fallback anchors" as the sanctioned mitigation, and `evals/phase1_baseline.md` confirmed `page_start` is `null` on every retrieved hit. That fallback remains valid as this change's terminal degradation path — this change is about making the non-fallback path actually work, not about removing the fallback.

## Goals / Non-Goals

**Goals:**
- Persist the full per-item provenance list from parse, not just a 50-item sample.
- Resolve real `page_start`/`page_end` on parent (section) chunk records via positional matching, avoiding the duplicate-heading-text collision in the current unused approach.
- Resolve tighter `page_start`/`page_end` on child (passage) chunk records by aligning paragraphs to the provenance rows that produced them, falling back to the parent's range when that finer alignment doesn't resolve.
- Make the degradation path explicit and inspectable via a `page_source` field, rather than an unlabeled `None`.
- Land this with zero required changes to `rag.py`, `cli.py`, or the Chroma indexing path.

**Non-Goals:**
- Guaranteeing page-perfect precision for every child chunk. This is best-effort positional matching over Docling's output, the same "best-effort" framing `_collect_provenance()`'s docstring already uses — not a guarantee.
- Reworking `_parse_sections()`'s H2/H3 splitting logic or `_pack_children()`'s packing logic. Provenance resolution wraps around the existing chunking shape; it doesn't change what a parent or child *is*.
- Re-deriving or improving Docling's own page-number accuracy — this change only threads through what Docling already reports.
- Anything in the `visual-kpi-vlm-extraction` change's `kpi_facts.jsonl` path — that gets page/figure provenance directly from VLM crop extraction and is untouched by this change.

## Decisions

### 1. Persist full provenance as a new sidecar file, not an expanded `meta.json` field
- **Choice:** `parse_report()` writes `corpus/parsed/{report_id}/provenance.json` containing the full `_collect_provenance()` output. `meta.json` keeps a small sample (for humans skimming it) plus `provenance_item_count`; it does not inline the full list.
- **Why:** `meta.json` is meant to stay small and scannable (it's read directly by `chunk_report()` today for `year`/`report_type`). A single-report provenance list can run into the hundreds of rows (485 for `2023_annual_en`) — that belongs in its own artifact, mirroring how `tables.md` already sits alongside `document.md` as a sidecar rather than being embedded in `meta.json`.
- **Alternatives considered:** Inline the full list in `meta.json` (rejected — turns a scannable summary file into a large opaque blob); re-run Docling inside `chunk_report()` to regenerate provenance on demand (rejected — expensive, and breaks the existing idempotency/rebuild contract that chunk artifacts regenerate from parse *artifacts*, not from PDFs).

### 2. Positional matching for parent (section) pages, not text-equality matching
- **Choice:** Filter `provenance.json` to rows labeled `section_header`, in document order. Filter `_parse_sections()`'s headings, in document order. Zip them pairwise: the *i*-th section-level heading gets the *i*-th `section_header` provenance row's pages.
- **Why:** Avoids the duplicate/short-heading-text collision that breaks the existing `heading_page_map()`'s dict-by-text approach. Both lists are produced from the same document in the same read order, so position is a more reliable join key than text content once Docling has already tokenized headings into discrete items.
- **Reconciliation:** If the heading count and `section_header` anchor count diverge (e.g. Docling emits a `section_header` for something `_HEADING_RE` doesn't match, like an H1 document title, or misses one `_parse_sections()` catches), stop pairing at the point of divergence rather than guessing — sections past that point fall through to the "unresolved" state (see Decision 4). A silently wrong page is worse than a missing one.
- **Alternatives considered:** Keep exact-text matching (rejected — known collision risk, demonstrated above); fuzzy/substring text matching (rejected — adds complexity and a new failure mode — partial matches across genuinely different sections — for a problem positional matching solves more simply, given both streams are already in matching document order).

### 3. Paragraph-to-provenance alignment for child (passage) pages
- **Choice:** Within each section, filter provenance rows to non-heading, non-picture labels (`text`, `list_item`) in document order. As `_split_paragraphs()` / `_pack_children()` pack paragraphs into a child, track which provenance rows' text fed that child (by the same document-order positional walk as Decision 2, scoped to the section). A child's `page_start`/`page_end` = min/max pages across the rows that contributed to it.
- **Why:** Gives citations that point at the actual page a paragraph came from, not just "somewhere in this section" — materially better for a multi-page section, and for Phase 3/4 consumers that will cite chunk-level facts.
- **Alternatives considered:** Only resolve parent-level pages and have every child inherit the parent's full range unconditionally (rejected as the *only* mechanism — it's cheaper but throws away precision that's available for free from provenance already computed; kept as the fallback for cases where paragraph-level alignment doesn't resolve, per Decision 4).

### 4. Explicit fallback chain with a `page_source` field
- **Choice:** Resolution attempts, in order: (a) child-level positional match → `page_source: "matched"`; (b) if (a) doesn't resolve, inherit the parent's resolved range → `page_source: "inherited"`; (c) if the parent itself didn't resolve, leave `page_start`/`page_end` as `None` and rely on the existing section-heading citation fallback already handled by `rag.py`.
- **Why:** Silent degradation is what created ambiguity in the first place (a `None` today could mean "Docling gave no page data" or "our matching logic failed" — indistinguishable). Making `"inherited"` vs `"matched"` explicit lets a downstream consumer — especially Phase 3's Neo4j fact extraction — decide whether a coarser, section-level citation is acceptable for a given use, rather than treating every populated `page_start` as equally precise.
- **Alternatives considered:** Binary matched/unmatched with no "inherited" state (rejected — throws away the still-useful parent-level signal); raising/failing chunking when matching fails (rejected — contradicts the project's existing "fail closed on generation, not on ingestion" posture; an unresolved page should degrade to the existing section fallback, not block chunk production).

### 5. Remove `heading_page_map()` rather than repurpose it
- **Choice:** Delete the existing unused function; the positional-matching logic lives directly in `chunk_report()`'s new helper(s) instead.
- **Why:** `heading_page_map()`'s signature and matching strategy (text-keyed dict over the *full* provenance list, mixing heading and non-heading rows into one flat map) don't fit the section-scoped, positional, dual-granularity approach here. Repurposing it would mean rewriting its body entirely while keeping a signature shaped for the old approach. It was never called from anywhere in the codebase, so removing it has no callers to migrate.
- **Alternatives considered:** Keep it as dead code for reference (rejected — the project has no other precedent for unused helpers, and it would be actively misleading next to the new logic it was superseded by).

## Risks / Trade-offs

- **[Risk] Heading/anchor count divergence leaves some sections unresolved** → Mitigation: this is the designed degradation path (Decision 2/4), not a failure state; those sections keep working today's section-only citation. Worth measuring against the real 8-report v1 corpus during implementation to see how common divergence actually is.
- **[Risk] Paragraph-level alignment is noisier than heading alignment** (tables extracted separately into `tables.md`, pictures breaking the provenance sequence mid-section) → Mitigation: fallback to parent-inherited range (Decision 4) rather than leaving children unresolved when finer alignment fails.
- **[Risk] Re-chunking existing artifacts changes chunk content indirectly** — `chunk_report()` is idempotent by `force` flag; re-running it with `force=True` on all 8 v1 reports must produce identical `chunk_id`/`text` fields and only add/populate the page fields, or downstream Chroma IDs will silently orphan. → Mitigation: verify chunk_id/text stability before/after as an explicit implementation check, not just page-field correctness.
  - **Found (implementation):** `chunk_id` was fully stable across all 8 reports (zero mismatches — no Chroma ID orphaning risk). `text` was byte-identical for 6/8 reports; 2 reports (`2020_annual_en`, `2021_annual_en`) each had 2 records (1 parent + its 1 child) differ by a handful of characters. Root cause was not `chunk_report()` itself but an upstream side effect of task 1.3/1.4: those 2 reports needed a full Docling re-*parse* (to backfill `provenance.json`, since it didn't exist pre-change), and Docling's RapidOCR produced slightly different OCR output on a second run over the same PDF pages (one 1-character table-row length diff, one single-character misread `"CMA CGM"` → `"CHA CGM"`). This is OCR non-determinism in the parse step, not a chunking regression — but it's a previously-unflagged risk of this change's migration path (re-parsing to backfill the new sidecar can itself perturb `document.md`, not just add `provenance.json`).
- **[Trade-off] Best-effort precision, not guaranteed accuracy** → Accepted per Non-Goals; matches the project's existing "best-effort" framing for provenance and the golden-eval baseline's qualitative (not automated-scoring) verification approach.

## Migration Plan

1. Implement `provenance.json` persistence in `parse_report()`.
2. Implement parent-level positional matching in `chunk_report()`.
3. Implement child-level paragraph alignment + fallback chain + `page_source` field.
4. Remove `heading_page_map()`.
5. Re-run `parse_report(force=True)` is **not** required — `provenance.json` needs the already-parsed Docling output, which exists; re-running `chunk_report(force=True)` alone suffices since `parse_report()`'s new sidecar write only needs to happen once per report going forward (existing `document.md`/`meta.json` are untouched, so `parse_report()`'s idempotency check needs to also account for `provenance.json` not existing yet on already-parsed reports — see tasks).
6. Rebuild `corpus/chunks/{report_id}.jsonl` for all 8 v1 reports; spot-check resolved pages against real PDFs and against `evals/phase1_baseline.md`'s previously observed citations.
7. Rebuild the Chroma index (`index_corpus.py --v1-batch --reset`) so served citations reflect the new page data.

Rollback: delete the new `provenance.json` sidecars and regenerated `corpus/chunks/*.jsonl`; `chunk_report()` reverts to hardcoded `None` if the code change is reverted, and existing `document.md`/`meta.json` are never modified by this change, so rollback doesn't touch parse outputs.

## Open Questions

- How often does heading/`section_header`-anchor count divergence actually occur across the 8 v1 reports? Affects how much of the corpus lands on the "matched" vs "unresolved" end of the fallback chain — worth a quick measurement pass early in implementation before assuming the happy path dominates.
  - **Measured (implementation, 8-report v1 corpus):** parents 1073/1076 matched (99.7%), 3 unresolved (0.3%). Children 1007/1147 matched (87.8%), 137 inherited (11.9%), 3 unresolved (0.3%). Divergence between heading count and `section_header` anchor count is rare in practice; the fallback chain is exercised almost entirely at the child level (paragraph/provenance-row misalignment from tables and pictures breaking the passage sequence), where it behaves as designed — 99.7% of children land on `matched` or `inherited`.
- Should `page_source` also distinguish "unresolved" as its own explicit value (vs. just omitting the field / leaving it `None` alongside null pages)? Leaning toward making it explicit for symmetry, but deferring to implementation.
- Does `_format_context()` / the citation prompt template in `rag.py` need updating later to show a page *range* (`page_start`–`page_end`) instead of just `page_start` for multi-page children, or is single-page-start citation sufficient for now? Out of scope for this change but worth flagging for a follow-up.
