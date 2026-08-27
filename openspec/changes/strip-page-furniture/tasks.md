## 1. Parse-time item capture (foundation)

- [ ] 1.1 Extend `parse.py::_collect_provenance()` (or a new function alongside it) to call `document.iterate_items(included_content_layers=set(ContentLayer))` instead of relying on the default BODY-only view, so every item (including `FURNITURE`-layer) is captured
- [ ] 1.2 For each item, capture normalized bounding-box position (`top_frac`/`bottom_frac`/`left_frac`/`right_frac`, relative to page height/width — not raw pixel values), `label`, `content_layer`, `text`, and `page_no`
- [ ] 1.3 Detect multi-column/2-up page layout dynamically per document (e.g. from page aspect ratio relative to a single-page baseline), rather than hardcoding `2020_annual_en`'s specific split, and fold the result into the x-band signal so two independently-repeated elements in different halves don't collide at the same y-band
- [ ] 1.4 Write a `corpus/parsed/{report_id}/items.jsonl` sidecar with the full per-item record, for audit and reuse by the fusion signal

## 2. Fuzzy text-matching primitive (shared, tuned independently per consumer)

- [ ] 2.1 Implement digit-normalization plus a character-level similarity ratio tolerant of OCR/extraction corruption (not exact-match-after-normalization alone)
- [ ] 2.2 Validate the similarity function against the corpus's known garbled instances as concrete regression cases: `2021_annual_en`'s cipher-garbled footer text and the page-14 OCR glitch
- [ ] 2.3 Expose an occurrence-clustering helper: group items within one document by normalized-text similarity, with counts

## 3. Point 1 — fused furniture-detection signal (`parse.py`)

- [ ] 3.1 Implement position-consistency scoring: cluster candidate items by (normalized text similarity OR (y-band, x-band) proximity), and score each cluster's bbox variance across its occurrences
- [ ] 3.2 Implement the 2-of-3 fusion decision as a pure function taking one item's signals (Docling flag, text-repeat corroboration, position corroboration) and returning a classification plus which signals fired: Docling+text-repeat is definitive (fast-track, no position check needed); text-repeat+position is furniture; Docling+position (text singleton) is furniture; any single signal alone is NOT furniture
- [ ] 3.3 Wire the fusion decision into `parse.py::parse_report()`: strip classified-furniture items from the exported Markdown before writing `document.md`
- [ ] 3.4 Record every considered item's classification decision (furniture or not, which signals fired) in `items.jsonl`, so stripped and flagged-but-kept items are both auditable
- [ ] 3.5 Keep all thresholds (similarity cutoff, position-variance bar, minimum occurrence count expressed as a fraction of document pages/headings, not a fixed integer) as named constants in one place, each documented with its empirical basis from `design.md`

## 4. Point 2 — running-header and running-subtext folding (`chunk.py`)

- [ ] 4.1 Add a first pass over `chunk.py`'s heading stream that builds a registry of `section_header`-labeled heading text (fuzzy-normalized) and occurrence counts across the document, independent of Point 1's signal (no bbox involved)
- [ ] 4.2 Add the second pass: a family's first occurrence stays as a real parent boundary; every later occurrence of a registered family folds into the currently-open section (no new parent opened, heading text not re-emitted as content)
- [ ] 4.3 Implement running-subtext detection: for the line(s) immediately following a registered running-header occurrence, check whether they themselves independently repeat (fuzzy-matched) under other occurrences of the same family; drop on repeat occurrences, keep only under the family's first occurrence
- [ ] 4.4 Confirm distinct-but-topically-related headings (e.g. `"7. PROPERTY AND EQUIPMENT"` vs. `"... (CONTINUED)"`) are NOT folded by this mechanism — only fuzzy/verbatim repeats of the same heading family are, per `specs/parent-child-chunking/spec.md`'s "Distinct headings ... are not folded" scenario

## 5. Overfitting guardrails / validation

- [ ] 5.1 Leave-one-report-out check across all 8 reports: for each report held out, confirm Point 1 and Point 2 behave sensibly using signal logic derived from the other 7 (no wildly divergent output on the held-out report)
- [ ] 5.2 Re-run the frequency-scan contamination measurement from `design.md`'s Context (the 14.8%-of-child-chunks metric, `scripts/scratch/boilerplate_scan.py` as a starting point) against the corrected corpus and record before/after
- [ ] 5.3 Spot-check the `2020_annual_en` Note 7 fragmentation example specifically: confirm it now produces 1 parent chunk instead of 5
- [ ] 5.4 Spot-check that the two known Docling false positives (the Africville Museum photo caption in `2023_annual_en`, the "*Based on TEU" footnote) are NOT stripped by the fused signal

## 6. Re-parse / re-chunk / reindex / eval

- [ ] 6.1 Re-parse all 8 v1 reports with `force=True`, regenerating `document.md`, `meta.json`, and the new `items.jsonl` sidecar
- [ ] 6.2 Re-chunk all 8 reports with `force=True`, regenerating `corpus/chunks/*.jsonl`
- [ ] 6.3 Reindex `data/chroma` against the corrected chunks
- [ ] 6.4 Add an addendum to `evals/phase1_baseline.md` re-running the golden subset (especially `gq-012`, `gq-019`) against the corrected corpus, following the `nomic-embed-task-prefixes` change's "numbers moved, here's why" pattern

## 7. Wrap-up

- [ ] 7.1 Confirm no unintended changes to `ask()`, `cli.py`, or the embedding scheme — this change is scoped to parse/chunk only
- [ ] 7.2 Note the deferred learned-classifier alternative and its prerequisite (a hand-labeled eval set) as explicit future work in a follow-up note, not lost
- [ ] 7.3 Flag the still-open sequencing question with `typed-retrieval-tools` (`design.md` Open Questions) for whoever picks up either change next
