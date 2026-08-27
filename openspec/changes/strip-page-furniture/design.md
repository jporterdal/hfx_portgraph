## Context

`parse.py::parse_report()` converts each PDF via Docling's `DocumentConverter` and writes
`document.export_to_markdown()`'s output verbatim to `corpus/parsed/{report_id}/document.md`, with
no post-processing. `chunk.py::_parse_sections()` then splits that markdown purely on `^(#{2,3})\s+`
lines (`chunk.py:17`), treating every match as a new section boundary with no awareness of whether
the same heading text has already appeared earlier in the document.

Repeated PDF page furniture (running headers/footers, letterhead, address blocks) is not being
separated from body content anywhere in this pipeline. Concretely, for `2020_annual_en`:

```
1701:## 7. PROPERTY AND EQUIPMENT
1742:## HALIFAX PORT AUTHORITY - NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS   <- furniture, not a real heading
1746:## 7. PROPERTY AND EQUIPMENT                                                 <- same note, treated as new section
1786:## HALIFAX PORT AUTHORITY - NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS   <- furniture
1790:## 7. PROPERTY AND EQUIPMENT (CONTINUED)
```

One logical note becomes 5 disconnected parent chunks. The repeated line itself occurs 23 times in
this document (of 221 total `##`/`###` headings — 10%), and the pattern (a report-specific
running-header variant, 20-26 occurrences) is present in all 8 v1 reports' parsed markdown, most
concentrated in the financial-notes portions.

**Correction to an earlier finding in this investigation.** Docling's own document model was
initially checked via `document.iterate_items()` called with no arguments, concluding every item
has `content_layer == ContentLayer.BODY` (no item classified `FURNITURE`) and that the repeated
financial-notes running header specifically carries `label == 'section_header'`, not
`PAGE_HEADER`. That conclusion was itself an artifact of the check: `iterate_items()` and
`export_to_markdown()` both default `included_content_layers=None`, which resolves to
`DEFAULT_CONTENT_LAYERS = {ContentLayer.BODY}` (`docling_core.types.doc.document`) — furniture-layer
items are silently excluded unless `included_content_layers=set(ContentLayer)` is passed
explicitly. Every probe run in this investigation up to that point made that same default call, so
all of them were structurally blind to anything Docling had already correctly classified as
furniture.

Re-running `2020_annual_en.pdf` with `included_content_layers=set(ContentLayer)` shows the real
picture is mixed, not uniformly negative:

```
498  text            BODY
221  section_header  BODY
121  list_item       BODY
 42  page_footer     FURNITURE   <- real, correctly detected, never reaches document.md
 24  page_header     FURNITURE   <- real, correctly detected, never reaches document.md
 14  caption         BODY
  2  footnote        BODY
```

The financial-notes running header ("HALIFAX PORT AUTHORITY - NOTES...") is unaffected by this
correction — re-checked under the full view, all 23 occurrences remain `section_header`/BODY; it
really is misclassified, same as originally found. But a separate, per-page running header/footer
family (`"PORT OF HALIFAX | ANNUAL REPORT | <section> | <page#>"`, varying per page) is correctly
detected 66 times (42 footer + 24 header) as `ContentLayer.FURNITURE` — and because
`parse.py::_export_markdown()` calls `document.export_to_markdown()` with no arguments, it already
inherits the same BODY-only default and silently drops all 66 for free, with zero code change
needed: no instance of that per-page footer/header text appears anywhere in
`corpus/parsed/2020_annual_en/document.md`. A visually-similar but textually shorter variant with no
section/page suffix (`"PORT OF HALIFAX | ANNUAL REPORT"` alone, 6 occurrences) is a genuine separate
miss — `label='text'`, `content_layer=BODY` in all 6 cases, even under the full view — and does leak
into chunks (`2020_annual_en::child::00003`, `::00223`).

Docling supports the header/footer distinction in general (`DocItemLabel.PAGE_HEADER`/`PAGE_FOOTER`,
`ContentLayer.FURNITURE`, and an `included_content_layers` filter on both `iterate_items()` and
`export_to_markdown()`), and — corrected from the original finding — its layout model does apply it
correctly some of the time on this corpus. It just isn't reliable enough to depend on alone (see the
`2021_annual_en` consistency check below), so detection still has to be added in this project's own
pipeline as the authoritative signal, with Docling's own furniture flag at best a weak, non-required
assist.

A secondary, milder effect: footer/address/boilerplate text (not just the repeated heading) also
lands inline inside otherwise-legitimate child chunk text. A frequency scan (any line repeating
3+ times verbatim within one report's parsed markdown, digits normalized to `#` so page numbers
don't prevent matching) found 170/1147 child chunks (14.8%) affected corpus-wide, at 0.3-1.3% of
characters within those chunks — see `proposal.md` for the per-report breakdown.

Per-chunk, this frequency scan's most- and least-contaminated child chunks
(`scripts/scratch/boilerplate_top_bottom_chunks.py`) show the two effects above are really one
mechanism at two boundary sizes: `chunk.py::_parse_sections()` opens a new section at *every*
occurrence of a repeated `##` heading, so a section's boilerplate fraction depends purely on how
much real content happens to sit before the next heading closes it. When the next heading follows
almost immediately, the section is furniture-only (`2020_annual_en::child::00117` etc. — 10 chunks
at exactly 100%, 8-45 chars, `text` = only the furniture sub-line `"December 31, 2020 (expressed
in CAD $, 000's)"`, `heading` = the repeated running header). When real content intervenes before
the next heading, the same furniture lines contribute only 1-2% of a chunk that's otherwise
legitimate (`2021_annual_en::child::00049` etc.). Fixing the heading-repeat boundary (Option B/D)
would eliminate the fully-degenerate tier entirely, since there'd be no boundary there to spawn a
chunk from — but the non-heading furniture line sitting *under* the heading (the date/masthead
line, not itself a `##`) would still land in whatever section it gets folded into, so the milder
tier needs a content-level strip in addition to the boundary fix, matching Option D's framing
below. One frequency-scan hit inspected this way was a false positive worth flagging for whichever
option gets implemented: `2020_annual_en::child::00113` flags "Director" (5x in the document) as
boilerplate purely because it recurs under different board members' bios — a live example of the
short-repeated-phrase false-positive risk Option A's trade-off already calls out.

Docling's own `ContentLayer.FURNITURE` assignment was traced to its source
(`docling/models/stages/reading_order/readingorder_model.py`) to check whether any pipeline option
could get it applied here: it's a hard pass-through of the layout model's per-item label —
`if c_label in (PAGE_HEADER, PAGE_FOOTER): content_layer = FURNITURE`, with no geometry or
position logic anywhere in Docling's own code. Whichever layout-model checkpoint runs (`heron`,
`egret_{medium,large,xlarge}`, etc. — all share the same 17-class taxonomy including
`Page-header`/`Page-footer`) either classifies a region as one of those two labels or it doesn't;
there's no tunable threshold or geometric override to reach for. Swapping checkpoints is a bet that
a different training run happens to relabel this specific text, unverified and requiring a new
model download per candidate.

What *is* already available, for free, on every item Docling produces regardless of label: each
`ProvenanceItem.prov` entry carries a full `bbox` (`l/t/r/b`, `coord_origin`), and each `Page`
carries `size`. `parse.py::_collect_provenance()` currently reads `page_no` off `prov` and drops
`bbox` entirely (`parse.py:30-37`). Re-running the converter and capturing that discarded bbox
(`scripts/scratch/docling_bbox_probe.py`, `docling_bbox_probe_footer.py`) shows it's a sharper
furniture signal than text-frequency alone:

```
2020_annual_en - "HALIFAX PORT AUTHORITY - NOTES TO..." heading, 23 occurrences
  21/23 at top_frac == 0.1006 exactly (4 decimal places) across pages 32-43
  vs. one-off real headings in the same doc: top_frac scattered 0.1352-0.7627

2021_annual_en - "Halifax Port Authority (dot) Annual Report 2021" footer, 16 occurrences,
  scattered across pages 4-99 (non-consecutive, spanning multiple sections)
  top_frac == 0.9342 on ALL 16 occurrences (spread: 0.0000)
```

The footer case also surfaced a concrete argument for position over text-matching: one of the 16
occurrences (page 14) is OCR/encoding-garbled (`"Halifax Port Authority ƀ Annual Report 2 2"` vs.
`"∙ ... 2021"` everywhere else). Digit-normalized text-frequency matching would not group it with
the other 15 — it normalizes to a different string. Position-based matching catches it without
looking at the text at all, since it sits at the identical bbox coordinate as every other
occurrence.

A follow-up check, prompted by visually confirming via `--debug-visualize-layout`
(`scripts/scratch/layout_viz_2021_annual_en/`) that this same footer *is* drawn with a
`PAGE_FOOTER (0.91)`/`(0.90)`/`(0.89)` label on pages 20, 38, and 39, found two things at once —
Docling's own detection of this footer is genuinely inconsistent, and the reason is more interesting
than a coin flip. Re-running `2021_annual_en.pdf` with `included_content_layers=set(ContentLayer)`
and matching on the literal substring `"Halifax Port Authority"` finds 25 occurrences, split:

```
 9/25 (36%)  page_footer  FURNITURE   <- correctly detected, silently excluded from document.md
16/25 (64%)  text         BODY        <- missed, leaks into document.md and chunks
```

But that substring match itself undercounts: pages 20 and 39 are *also* correctly labeled
`page_footer`/`FURNITURE` by the layout model, and were invisible to that count because their
extracted text is severely garbled — `'DDhebDt Lknp $qpdknepu ƀ $jjqDh Nalknp .,.-'` (page 20) and
`'37 DDhebDt Lknp $qpdknepu ƀ $jjqDh Nalknp .,.-'` (page 39) for what renders visually, and reads to
a human in the debug image, as `"Halifax Port Authority ∙ Annual Report 2021"`. Page 38's occurrence
by contrast has clean text (`label=page_footer` too). All three — clean-text page 38, garbled-text
pages 20 and 39 — sit at the identical `top_frac == 0.9342` as every other occurrence, correctly
detected or not. So: the layout model's `PAGE_FOOTER` classification is driven by geometry, not by
the (sometimes badly corrupted) text layer, which is exactly why it still fires correctly on pages
20 and 39 despite the text extraction being unusable there. A text-based project-level detector —
including the frequency scan this investigation has used throughout, and the substring match just
described — cannot find what it cannot read; it would miss these two the same way it missed the
page-14 OCR glitch, only more severely. Position-based detection is blind to this failure mode
entirely, since it never looks at the text to begin with. Combined with the inconsistency finding
above, this is the strongest evidence in this investigation that Docling's own furniture flag should
be treated as a bonus signal at most, not a dependency — a project-level detector (position-based,
per Option C) needs to be the thing that reliably catches all of these regardless of what Docling's
layout model or text extraction happen to do on a given page. (This is a **recall** argument — Docling
misses too much to depend on alone. See the corpus-wide **precision**/false-positive check below,
which finds the flag is considerably more trustworthy on that axis than "bonus signal" implies, once
corroborated.)

A full sweep of all 100 pages (matching by position — `top_frac == 0.9342 ± 0.003` — rather than by
text, so it isn't blind to garbled instances the way the two counts above are) confirms and sharpens
this (`scripts/scratch/docling_2021_footer_full_sweep.py`):

```
100 pages total; 92 have a footer-position candidate, 8 don't (likely divider/image pages)
96 footer-line instances total (4 pages had 2 candidates - see false positive below)

76/96 (79%)  correctly detected as page_footer/FURNITURE
20/96 (21%)  missed - labeled text/BODY

25/96 (26%)  clean, readable text
71/96 (74%)  garbled text          <- most of this document's footer text is corrupted, not occasional

correctly-detected + clean:    9    missed + clean:     16
correctly-detected + garbled: 67    missed + garbled:    4
```

Two things the full sweep adds beyond the smaller samples above. First, garbling is the *majority*
case in this document (74%), not a rare glitch, and it's regional: clean text clusters in pages
3-48 (the narrative section), while pages ~49 onward (financial-statements territory) are almost
entirely the corrupted cipher, with a third, slightly different substitution table appearing on
pages 87 and 92 specifically — meaning more than one broken font subset is embedded in this single
PDF. Detection remains strongly geometry-driven throughout: garbled text is still correctly detected
94% of the time (67/71), while — counter-intuitively — clean text is only detected 36% of the time
(9/25), consistent with the smaller sample above and not an artifact of it.

Second, the position-matching approach itself produced one genuine false positive, which is exactly
the risk Option C's trade-off already named in the abstract and now has a concrete corpus example
for: pages 81-84 each have a second candidate at the identical y-band that is *not* the footer at
all — a real, unrelated footnote block (`"Adjustments represent the removal of costs and
accumulated..."`) that happens to end at the same page-relative height on those specific
financial-statement pages. A pure position-only detector would misfire on this; it needs pairing
with some form of cross-page repetition or pattern check (the normalized-text-frequency signal this
investigation has used throughout is one candidate) to reject a one-off content block that merely
happens to share a furniture element's typical position.

**Corpus-wide check: does Docling's FURNITURE flag itself produce false positives?** The pages
81-84 false positive above is a false positive for *position-only* detection, not for Docling's own
flag. Worth checking separately, and corpus-wide rather than on the two documents this investigation
has focused on so far: does Docling's `page_header`/`page_footer` labeling ever fire on real content?
`scripts/scratch/furniture_fp_corpus_sweep.py` re-converts all 8 v1 reports with
`included_content_layers=set(ContentLayer)` and, for every item labeled `page_header`/`page_footer`
(`content_layer=FURNITURE` — the label→content_layer pass-through this investigation already traced
in `readingorder_model.py` holds for all 516 such items across the corpus, confirming that trace
generalizes beyond the single document it was found on), checks whether its digit-normalized text
repeats elsewhere in the same document. A repeat is strong corroborating evidence it really is
furniture; a singleton (no repeat anywhere in the document) is the interesting case, since Docling's
flag is then the *only* signal backing it:

```
516 FURNITURE items across 8 reports
505/516 (97.9%)  repeat elsewhere in the document — corroborated by text-repetition too
 11/516 (2.1%)   singleton — no other occurrence; Docling's flag alone is all there is
```

Eyeballing all 11 singletons individually (full list:
`scripts/scratch/furniture_fp_corpus_sweep_summary.txt`) rather than trusting the count alone: 9 of
the 11 are not really false positives — they're already-known furniture families (the
`2020_annual_en` 2-up-page duplication artifact from Option C above, `2021_annual_en`'s
garbled-cipher masthead, doubled/merged page-number+footer text) that only fail the text-repeat test
because Docling's own text extraction fused, doubled, or garbled them into a string that no longer
exact-matches their siblings — a measurement artifact of the repeat-check, not a labeling error. Two
are genuine: `2023_annual_en` page 27, `"Pictured: the Africville Museum (photo credit: Tourism Nova
Scotia/Dean Casavechia)"` — a real, substantive photo caption sitting at the bottom of the page,
labeled `page_footer` purely by position; and, more borderline, `2023_annual_en` page 7, `"*Based on
TEU"` — a chart footnote, thin but arguably real informational content rather than boilerplate.

So the "bonus signal at most" framing above was a **recall** argument: Docling's flag alone still
misses the majority of a document's furniture instances when its own detection is inconsistent (the
79%-detected finding on `2021_annual_en`). On **precision**, the picture is considerably stronger:
false positives exist but are rare (~0.4% of flagged items, 1-2 per ~500) and pattern-specific — both
the genuine and borderline cases are bottom-of-page captions/footnotes sharing a footer's typical
position, the same failure mode already identified for position-only detection at pages 81-84.
Combined with a corroborating signal, the flag is considerably more trustworthy than "bonus" implies:

- **Docling FURNITURE + the same text (fuzzy-matched) repeating elsewhere in the document** —
  corroborated by both signals at once, and covers 505/516 (98%) of everything Docling flags. Treat
  as **definitive**: no further check needed.
- **Docling FURNITURE + consistent bbox position across other pages, but no text repeat** (the
  singleton case) — a **reasonably strong** signal (9 of 11 singletons were still genuine furniture,
  just extraction-mangled), but not definitive on its own, since this is exactly the slice where both
  the genuine and borderline false positives live. Bears further consideration as part of the
  fusion-rule design (Option C / the combined signal discussed below).

This refines rather than overturns the "bonus signal" framing: Docling's flag is unreliable for
*recall* (a project-level detector is still needed to catch what Docling misses) but precise enough,
once corroborated by text-repetition, that it should anchor the fused signal for that slice rather
than merely assist it.

## Goals / Non-Goals

**Goals:**
- Characterize both furniture problems (as-heading, in-content) precisely enough that an
  implementation approach can be chosen with a clear understanding of what it needs to catch and
  what it risks over-catching.
- Establish a repeatable measurement (the frequency-scan method used here) so any future fix's
  effectiveness — before/after contamination rate — can be verified rather than eyeballed.
- Surface the mechanism (heading-as-boundary in `chunk.py`, verbatim export in `parse.py`,
  Docling's layout-model miss) clearly enough that a future design pass can pick an option without
  re-deriving this investigation.

**Non-Goals (for this change):**
- ~~Choosing or implementing a specific mitigation — deferred to a follow-up change once an option
  below is selected. This is why `tasks.md` is intentionally omitted here.~~ **Superseded** — a
  follow-up design pass (below) selected and scoped an approach in the same change rather than a
  separate one; `tasks.md` now exists.
- Reindexing `data/chroma` or re-running `evals/phase1_baseline.md` are still consequences of
  *implementing* `tasks.md`, not of this design pass — they happen during task execution, not here.
- Fixing Docling's own layout-model header/footer detection (upstream, out of this project's
  control) — mitigations here work regardless of whether that ever improves.
- Training a learned classifier over the three signals — considered directly (see "Rejected
  alternative" below) and deferred, not pursued as part of this change.

## Decisions

Two distinct problems, two distinct mechanisms — confirmed during the design pass, not merged into
one classifier despite both hinging on "repeats across pages." A page header/footer/masthead is
content-free chrome; a running section heading is real document structure that Docling identifies
*correctly* but whose repetition still needs to not fragment chunking. They warrant different
signals and live in different parts of the pipeline.

### Decision 1 — Point 1 (page furniture): fused 2-of-3 signal, Docling+text fast-tracked

Selected: a synthesis of Option C (bbox position-consistency) with the text-repetition signal from
Options A/D and Docling's own FURNITURE flag (Option C's "bonus signal"), combined as follows:

- **Docling FURNITURE flag + fuzzy/normalized text repeats elsewhere in the document → furniture,
  definitive.** No further check needed. Empirically (see Context, `furniture_fp_corpus_sweep.py`)
  this covers 505/516 (98%) of everything Docling flags corpus-wide, with an estimated false-positive
  rate near zero on this slice.
- **Fuzzy text repeats + consistent (y-band, x-band) position across occurrences, no Docling flag
  needed → furniture.** Covers Docling's recall gap: the garbled/missed footer instances and
  `section_header`-mislabeled mastheads Docling's layout model doesn't flag as `page_header`/
  `page_footer` at all.
- **Docling FURNITURE flag + consistent position, but text is a singleton (no repeat) → furniture,
  reasonably strong but not definitive.** 9 of the corpus's 11 singleton FURNITURE items were still
  genuine furniture (extraction-mangled, not real content); the 2 real/borderline false positives
  found live in exactly this slice.
- **Any single signal alone (text-repeat only, position only, or a Docling-singleton with no position
  corroboration) → NOT classified furniture.** Left in output, not stripped. This is what rejects the
  named false-positive risks directly: the "Director" case (repeats, but position scatters across
  different bios) and the pages 81-84 footnote (matches a furniture position band, but doesn't
  repeat) both fail to clear 2-of-3 and are correctly left alone.
- Items are logged to a per-report audit sidecar regardless of the decision (stripped or not), so
  "flag but don't strip" is inspectable rather than silent, and so a stripped item is still
  traceable back to the source PDF for citation-provenance auditing (Option A's fidelity concern,
  addressed by keeping a record rather than by not stripping).

**Architecture:** classification happens in `parse.py`, which now captures a per-item structured
record (normalized bbox `top_frac`/`bottom_frac`/`left_frac`/`right_frac`, `label`, `content_layer`,
text, `page_no`) for *every* item via `included_content_layers=set(ContentLayer)` (not just the
current BODY-only default), not only headings. `parse.py` runs the fused-signal classification and
writes an already-furniture-stripped `document.md`, plus an `items.jsonl` sidecar (full per-item
record + the classification decision) for audit and reuse. `chunk.py` stays markdown-only for this
part, unchanged in shape. The alternative explored — making `chunk.py` itself item/bbox-aware — was
considered and set aside: Decision 3 below confirms Point 2 doesn't need bbox at all, which removes
the main reason `chunk.py` would need item-level awareness, so the smaller, more contained change
(classify once in `parse.py`) wins. Flagging this explicitly since it wasn't a unanimous close in
conversation — revisit if a future need for item-level data in `chunk.py` emerges.

**Overfitting guardrails (binding, not optional):**
- Thresholds are relative, not absolute: position-consistency is a variance-within-document check
  (e.g. bbox spread as a fraction of page height across a candidate's occurrences), not a fixed
  `top_frac` value; repeat-count bars should be expressed as a fraction of the document's total
  pages/headings, not a hardcoded integer (see Open Questions — this also means revisiting
  `document-parse/spec.md`'s current literal "three or more pages" wording).
- Document-specific structural properties (the 2-up-page layout found in `2020_annual_en`) are
  detected dynamically per document (e.g. from page aspect ratio), never hardcoded as a global
  assumption.
- Any remaining constants (fuzzy-match similarity threshold, minimum occurrence count) live as
  named, centrally-located, documented values — not scattered magic numbers — each with its
  empirical basis noted and an explicit expectation of re-tuning as the corpus grows.
- A leave-one-report-out check across the 8 available reports (tune/inspect behavior holding one
  report out) is part of validation (`tasks.md`) before this is considered corpus-general rather than
  corpus-fitted.

### Decision 2 — fuzzy text-matching primitive

Shared by both Point 1 and Point 2 (see Decision 3), but tuned/used independently per mechanism, not
via a shared classifier. Digit-normalization (existing) plus a character-level similarity ratio
tolerant of OCR/extraction corruption (the `2021_annual_en` cipher-garbling case), rather than exact
match after normalization alone. Exact similarity metric left to implementation, but must be
evaluated against the corpus's known garbled instances (see Context) as a concrete test case, not
tuned in the abstract.

### Decision 3 — Point 2 (running section headers): text-only, sequential registry, two-pass

Independent of Decision 1 — scoped to `section_header`-labeled items only, no bbox signal. Matching
is against a *registry* of previously-seen heading-text families (fuzzy-matched), not the literal
prior heading in document order — necessary because the corpus's real pattern interleaves a running
masthead header with distinct real headings (`7. PROPERTY AND EQUIPMENT` / `... (CONTINUED)`), so
"the previous heading" would never actually match itself.

- **Two-pass.** Pass 1 scans the full `section_header` stream, building the family registry and
  occurrence counts. Pass 2 walks the stream applying the fold decision: a family's first occurrence
  stays as the real section boundary; every later occurrence of that family folds into the
  currently-open section (not re-emitted as heading or content, does not start a new parent). Chosen
  over a single streaming pass because `chunk_report()` already loads the full document into memory
  before any of this runs (no I/O or memory cost to a second pass over a small heading list), and a
  streaming approach would need to either backpatch already-emitted sections once a family is
  confirmed running (a second pass in disguise, harder to test) or weaken the "repeats enough to
  count as running" bar to something looser than intended just to decide inline.
- **Running subtext.** A line immediately following a registered running-header occurrence is treated
  as running subtext — dropped on repeat occurrences, kept only under the family's first occurrence —
  only if that line *itself* independently repeats (fuzzy-matched) under other occurrences of the
  same family. Real content that merely happens to start right after a running header is never at
  risk: it won't independently repeat, so it's never candidate subtext.
- Explicitly out of scope for this mechanism: headings that are genuinely evolving text across a
  multi-page note (`7. PROPERTY AND EQUIPMENT` vs. `... (CONTINUED)`) are not verbatim/fuzzy repeats
  of each other and so are not folded by this mechanism — each still opens its own parent. Known gap,
  not solved here.

### Rejected alternative — learned classifier over the three signals

Considered: given the low-dimensional feature space (bbox variance, text-similarity score, repeat
count, Docling flag — not raw text or pixels), a small logistic-regression or 1-hidden-layer MLP
classifier was a live option, and had genuine pedagogical appeal. Not pursued for this change because
it has no prerequisite it can be built on yet: there is no independent, hand-labeled ground-truth set
to train or evaluate against, so a classifier trained on labels derived from the same three signals
would only learn a soft-weighted restatement of the rule above, not demonstrably improve on it. Doing
this properly would require hand-labeling a stratified sample (confident positives/negatives, hard
negatives like the "Director" and pages-81-84 cases, hard positives like the extraction-mangled
singletons, and the 2 known false positives as adversarial test cases) across all 8 reports, plus
leave-one-report-out validation to check generalization rather than corpus-memorization — real,
worthwhile work, but a separate follow-up, not a blocker for shipping the rule-based signal now.
Revisit if the rule-based signal's real-world precision/recall (once measurable post-implementation)
turns out to be unsatisfying.

## Options Under Consideration

**A. Frequency-based line stripping in `parse.py`.** Post-process `export_to_markdown()`'s output:
count normalized line frequency per document, drop lines above a repeat threshold before writing
`document.md`. Catches both problems (as-heading and in-content) in one pass, applied once at the
earliest point in the pipeline.
- *Trade-off:* destroys parse fidelity — `document.md` would no longer be a faithful full
  transcript of the source PDF, which matters for anyone auditing parse output against the PDF
  (`document-parse`'s "Preserve citation provenance" requirement doesn't currently promise
  completeness, but silently dropping text is a bigger behavior change than filtering headings).
  A repeat-count threshold is also a blunt instrument: could false-positive on a legitimately
  repeated short phrase (a recurring disclaimer, a repeated table column header) that happens to
  cross the threshold.

**B. Heading-repeat folding in `chunk.py::_parse_sections()`.** Track heading text seen earlier in
the same document; when a heading repeats, don't open a new parent section — fold its lines into
the currently-open section instead. Targets the higher-severity problem (structural fragmentation)
directly, and leaves `document.md` untouched (parse fidelity preserved; the "fix" is scoped to how
chunking interprets headings, not what was parsed).
- *Trade-off:* needs a first pass over the document's headings to know what "repeats" means before
  the second (splitting) pass runs, or an online/streaming heuristic that's harder to get right
  (e.g. what if the *first* occurrence of a running header should itself not start a section?).
  Does not address furniture-in-content at all — the address block / ISO cert text embedded inside
  otherwise-real chunks would be untouched.

**C. Position-based (bounding-box) furniture detection.** Extend `parse.py::_collect_provenance()`
(currently only extracts `page_no` from each Docling item's `prov`) to also capture bounding-box
position, and flag items that recur at a consistent page-relative position across many pages —
the structural definition of a running header/footer, independent of exact text repetition (would
catch a footer that includes a varying page number without needing digit-normalization tricks).
- *Trade-off:* originally scoped as the most-effort, least-verified option of the three ("requires
  understanding Docling's `prov`/bbox schema in more depth than this investigation went into, plus
  calibrating a tolerance"). That's now measured, not assumed (see Context): both known furniture
  lines in this corpus sit at a page-relative position with 0.0-0.6% variance across every
  occurrence, versus real headings scattered over 60+ points of page height — a wide, easy margin
  for a tolerance band. Remaining effort is smaller than originally scoped: capturing bbox is a
  ~5-line change to an existing function, and the schema is now understood well enough to write to.
  Still needs: combining the position signal with *some* text-repetition check (position alone
  would also flag a legitimately-repeated page number or table column header at a fixed spot — now
  confirmed concretely, not just hypothetically: the `2021_annual_en` full-page sweep in Context
  found a one-off footnote block on pages 81-84 sitting at the exact same y-band as the running
  footer, which a position-only rule would misfire on), and the page-35 case seen during this
  investigation — the same heading occurring twice on one page at two different positions — means
  "one candidate region per page" can't be assumed. Most likely of the three to generalize cleanly
  to a new report's differently-worded furniture, and — per the OCR-garbled and cipher-garbled
  footer occurrences found during this investigation, present on a *majority* (74%) of one report's
  footer instances — more robust than text-frequency matching even within the current corpus.

  Two more findings, from running Docling's own `--debug-visualize-layout` CLI flag against
  `2020_annual_en.pdf` (output: `scripts/scratch/layout_viz_2020_annual_en/`) to see the layout
  model's raw per-cluster output rather than only the exported `DoclingDocument`:

  - **The source PDF is a 2-up spread, not single pages, for almost the whole document.**
    `pdfinfo` shows 43 of 45 pages sized `1440 x 720 pts` — exactly double-width — versus
    `720 x 720 pts` for the front/back cover (pages 1 and 45 only). Docling treats each of those
    wide pages as one `page_no`, but it's really two independently-laid-out printed report pages
    side by side, each carrying its own copy of the running header at the same vertical position
    by construction (both halves are vertically aligned). This means the earlier "0.0-0.6% top_frac
    variance" finding is partly a mechanical artifact of the 2-up layout, not solely evidence of a
    universally consistent header position — page 32's debug render shows two independent
    `SECTION_HEADER` detections (confidence 0.83 and 0.82) for the same header text, one per half,
    followed by different real content in each half within a few lines. An implementation should
    key on **(normalized text, y-band, x-band/column)** rather than y alone, since two genuinely
    different repeated elements in different halves could otherwise collide at the same y-band. The
    page-35 double-occurrence noted above is a separate, real within-half-page repeat, not another
    instance of this 2-up artifact.

  - **Layout-model confidence scores don't survive into the exported document, so they're not a
    usable signal from where `parse.py` currently reads.** The debug overlay shows the header being
    classified `SECTION_HEADER` at 0.82-0.83 confidence — not borderline; the layout model is fairly
    sure of the wrong label, so a confidence threshold wouldn't have separated it out even if it
    were available. It isn't: `SectionHeaderItem` and `TextItem` (`docling_core.types.doc.document`)
    have no `confidence` field. The score lives only on the transient `Cluster` object inside
    `docling/models/stages/layout/layout_model.py::predict_layout()` and is dropped once
    `doc.add_heading()`/`doc.add_text()` runs — reaching it would mean hooking a deeper, less stable
    part of Docling's pipeline than `document.iterate_items()`, unlike bbox which is already
    attached to every exported item's `prov`.

**D. B, plus a narrow denylist-style strip for known non-heading furniture.** Do the `chunk.py`
heading-fold (B) for the structural problem, and separately strip a short, explicit list of known
non-heading boilerplate strings (the HPA mailing address, phone/fax numbers, ISO certification
number — these are near-identical across all 8 reports, confirmed during the frequency scan) from
child chunk text at chunk-build time, rather than mutating `document.md`.
- *Trade-off:* the denylist only catches furniture already seen in this specific corpus; a new
  report with different boilerplate text would need the list extended manually (lower generality
  than A or C, but lowest risk of over-stripping real content, and cheapest to implement and audit).

**Resolved — see Decisions above.** The chosen approach is a synthesis rather than a pick of one
listed option: Decision 1 substitutes C's position-consistency signal *into* a generalized version
of A/D's text-repetition check exactly as flagged below as a live possibility, fused with Docling's
own flag (elevated from "bonus" to "anchor, when corroborated" per the corpus-wide false-positive
check in Context); Decision 3 keeps B's heading-fold approach for the structural problem, but scoped
more precisely (registry-based, sequential, two-pass) than B's original framing left it. D's narrow
denylist idea is superseded by Decision 1's general fused signal, which covers known non-heading
furniture (address blocks, ISO cert numbers) without a corpus-specific denylist. The rest of this
section is kept as the historical record of the options actually compared, per this doc's existing
convention of preserving investigation history rather than overwriting it.

No option has been eliminated. A is the simplest and most complete but riskiest to fidelity; B is
the most targeted at the worse (structural) problem with the least risk; C is the most principled
long-term fix and, per the bbox measurements above, cheaper and better-verified than originally
scoped; D is B plus a cheap, low-risk patch for the milder problem that B alone leaves unaddressed.
C's detection signal (position-consistency) could also be substituted into B or D in place of — or
alongside — their text-repetition check, rather than treated as a fully separate option; not yet
decided whether that's worth doing given the current corpus's text-frequency signal already worked
well enough to characterize both problems.

## Risks / Trade-offs

- **[Risk]** Whichever option is chosen will change `corpus/chunks/*.jsonl` content and chunk
  boundaries for content that already has baseline eval numbers recorded against it
  (`evals/phase1_baseline.md`) — a second embedding-scheme-style "numbers moved, here's why"
  addendum will be needed after implementation, same pattern as the `nomic-embed-task-prefixes`
  change already went through.
- **[Risk]** Any heuristic (repeat-count threshold, bbox-position tolerance) needs calibration
  against this specific 8-report corpus and may not generalize automatically if new report types
  or PDF layouts are added later (e.g. a report from a different production pipeline/template).
- **[Trade-off]** Deferring the decision (this change) versus picking an option immediately: this
  keeps the investigation and the decision separable and reviewable, but means the actual fix (and
  its eval impact) doesn't land until a follow-up change is scoped and implemented.

## Open Questions

- Does fixing the structural fragmentation (Decision 3) measurably change `gq-019`'s
  `year_collision` outcome or `gq-012`'s evidence-swap behavior? Not yet tested — `tasks.md`'s
  validation step re-runs the golden subset; worth checking before assuming this is purely a
  corpus-quality fix with no eval-visible payoff.
- **Still open**: is a relative repeat-count/frequency threshold (Decision 1's overfitting
  guardrails) tuned on this 8-report corpus likely to hold up if more reports (different years,
  different report types, a different production template) are added to the manifest later? The
  leave-one-report-out check in `tasks.md` is a first read on this, not a full answer — it can only
  validate against variation already present across these 8 reports, not against a genuinely new
  template.
- **New**: `document-parse/spec.md`'s current scenario text hardcodes "repeats verbatim ... across
  three or more pages" — Decision 1 commits to relative thresholds instead. The spec wording needs
  updating to match (done as part of this change's spec delta), but the actual relative threshold
  value is an implementation-time judgment call, not fully pinned down here.
- **Should this change land before `typed-retrieval-tools` is implemented, not after?**
  `typed-retrieval-tools/design.md` Decision 3 builds a section-type classifier (footnote vs.
  primary statement, to fix `gq-019`'s `year_collision` failure) keyed entirely on each chunk's
  `heading`/`section` metadata — the exact field this change's Problem 1 (furniture-as-heading)
  corrupts for ~10-19% of chunks depending on report. A chunk whose `heading` is the repeated
  running header text matches neither the classifier's `^\d+\.\s` footnote pattern nor its
  `"Statement of"` keyword, so it falls through unclassified rather than being deprioritized the
  way a real footnote would be. Separately, `langgraph-plan-critique-loop/design.md` Decision 5's
  critic does a presence-only coverage check (does a year/report slot have ≥1 hit, not whether
  that hit is substantive) — a furniture-fragmented, content-starved chunk (like the rank-2 hit
  found for `gq-012`) can satisfy that check and reach the synthesizer as if the slot were properly
  covered. Neither Phase 2 design doc currently references this change (both predate this
  investigation by ~3 days) or its corpus-quality dependency. If `typed-retrieval-tools` is built
  and its section-classifier validated (`evals/typed_retrieval_validation.md`) *before* a furniture
  fix lands, that validation measures the classifier against corrupted ground truth, and a later
  furniture fix (options B/D reshape parent/child boundaries and chunk_ids) would require redoing
  the validation, not just re-running it. Building the furniture fix first would let the section
  classifier be validated against clean heading metadata from the start. Not yet decided which
  order is right — worth resolving before either Phase 2 change begins implementation (both are
  currently `completedTasks: 0`).
