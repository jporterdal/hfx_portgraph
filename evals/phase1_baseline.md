# Phase 1 naive RAG baseline

**Date:** 2026-08-09
**Status:** RUN — local Ollama (`llama3.1`, `nomic-embed-text`) reachable; index rebuilt from scratch.

## Setup

```bash
python scripts/index_corpus.py --v1-batch --reset
```

Indexed 1147/1147 child chunks (100% of `corpus/chunks/*.jsonl` children) across all 8 v1
`annual`/`financials` reports into a fresh `data/chroma/` collection. Per-report counts are even
(87–223 children/report); `2023_annual_en` is the smallest, consistent with the parse-gate note
that this report loses chart-borne figure content to Docling.

## Task 4.4 — smoke-ask (single_doc)

- `gq-005` ("containerized throughput ... 546,163 TEU"): `status: ok`. Answer correctly cites
  `[chunk_id=2023_annual_en::child::00036; section=CARGO; page_start=unknown]` and quotes the
  right figure. **Citations confirmed working.**
- `gq-003` (2023 operating income): retrieval was correct both times it was run (net earnings
  $13,841 2023 vs $13,815 2022 — matches `evals/phase1_parse_gate.md`), but the model's answer
  never included the required `[chunk_id=...]` inline citation, so `ask()`'s classifier marked it
  `answer_uncited` on both runs (not one-off sampling noise). See "Citation-format adherence" below.

## Task 5.1 — golden subset (includes gq-001)

| id | tags | status | notes |
|---|---|---|---|
| `gq-001` | yoy_metric, multi_hop, narrative, table_heavy (**flagship**) | `ok` | Retrieval surfaced 2020/2021/2022 evidence but **missed 2023 entirely**, and explicitly stated "no information provided on operating income" for any year. Confirms the design.md prediction: naive similarity-over-children cannot do the year-span join + metric-across-docs reasoning this question needs. This is the gap Phase 2 (planning/decomposition) is meant to close, not a bug. |
| `gq-002` | single_doc, narrative | `ok` | Correctly grounded 2022 strategic items (50-year Master Plan, Pier A-1 Infilling Project) with proper citations. Solid narrative retrieval. |
| `gq-012` | multi_hop, narrative (no table) | `ok` | Reasonable 2021-vs-2023 comparison, properly cited both sides, though 2021-side evidence was thin (retrieval favored 2023 passages). |
| `gq-019` | year_collision, table_heavy, single_doc | `insufficient_evidence` | **Retrieval miss, correctly handled.** Query asked for the 2021 income-statement revenue figure; retrieval matched the literal phrase "17. Comparative figures" across *all four* financials docs (2020–2023) — the wrong footnote, not the statement of earnings. Model correctly declined rather than guessing from irrelevant evidence. This is the failure mode `year_collision` tags exist to catch: literal-phrase similarity beats semantic table identification. |
| `gq-003` | single_doc, table_heavy | `answer_uncited` | See 4.4 above — right evidence, no inline citation. |
| *(negative control)* | — | `insufficient_evidence` | `"What is the capital of France?"` → correctly declined. Retrieval still returned 6 chunks (Chroma always returns top-k), but at distance ≥1.01 vs 0.27–0.63 for on-topic queries — a clear separation band. Model did not cite or fabricate from the irrelevant hits. |

## Observations

- **Citation format has three distinct outcomes**, not two: `ok` (cited correctly), `insufficient_evidence`
  (model declines, sometimes correctly on a genuine retrieval miss), and `answer_uncited` (right
  evidence retrieved, model just drops the citation tag). The third bucket is a prompt-adherence
  gap in `llama3.1`, not a retrieval problem — worth a note for Phase 2 if it recurs, but not a
  Phase 1 blocker since `4.2`/`4.3` are about the mechanism existing, which they do.
- **Page-level citation is not yet real.** `page_start` is `null` on every single hit across all
  8 reports — confirmed this is a genuine gap in `corpus/chunks/*.jsonl` (chunk records themselves
  have `page_start: None`), not an `ask.py` display bug. Section-level citation (`section=`) is
  populated and accurate, so citations are traceable to a document + section, just not a page.
  Matches the risk already called out in `design.md` ("Weak or missing page numbers from parser").
- **Retrieval distance shows a usable separation band**: on-topic hits cluster ~0.27–0.63;
  off-topic (negative control) hits sit ≥1.01. Not wired into the pipeline as a hard cutoff, but a
  plausible future improvement to pre-filter obviously-irrelevant retrieval before it reaches the
  LLM.
- **Multi-hop / year-span questions (gq-001, gq-004, gq-007, gq-010, gq-014, gq-017, gq-022, gq-025
  by tag) are the expected Phase 1 ceiling.** Single-doc and even some cross-doc-but-shallow
  (gq-012) questions work; genuine multi-year joins do not. This matches `design.md`'s explicit
  non-goal ("LangGraph plan/critique loops (Phase 2)") and gives Phase 2 a concrete target: gq-001
  is the item to re-run once planning/decomposition exists.
- **`year_collision` tag earns its name.** gq-019 shows literal phrase overlap ("Comparative
  figures" as a heading) out-competing the semantically correct section ("Consolidated statement
  of earnings") in embedding space. Insufficiency fired correctly rather than hallucinating, which
  is the safe outcome, but the retrieval miss itself is a real naive-RAG limitation worth carrying
  into Phase 2/3 design discussions.

## 2026-08-24 update — task-prefixed nomic embeddings (`nomic-embed-task-prefixes`)

**Status:** RUN — local Ollama (`llama3.1`, `nomic-embed-text`) reachable; index rebuilt from
scratch via `hfx-index --reset --v1-batch` (1147/1147 child chunks) after `_embed_documents()` /
`_embed_query()` started applying nomic-embed-text's `search_document: ` / `search_query: `
task prefixes at the Ollama call boundary. **The numbers below are not directly comparable to the
run above** — that run's index was embedded without any prefix, this one's is fully prefixed
(no mixed-scheme collection exists), so both the distance scale and retrieval ranking shifted.

| id | tags | status (old → new) | notes |
|---|---|---|---|
| `gq-001` | yoy_metric, multi_hop, narrative, table_heavy (flagship) | `ok` → `answer_uncited` | Retrieval still surfaces only 2020–2022 evidence in the top 6 (distances 0.545–0.606) — 2023 is still missing, same substantive gap as before. Status label changed because the model's answer this run omitted the `[chunk_id=...]` citation tag, not because retrieval got worse; the year-span join is still the expected Phase 1 ceiling per design.md. |
| `gq-005` | single_doc, narrative, table_heavy | `ok` → `ok` | Same outcome. Still correctly cites `[chunk_id=2023_annual_en::child::00036; ...]` for the 546,163 TEU figure. |
| `gq-002` | single_doc, narrative | `ok` → `answer_uncited` | Retrieval quality looks comparable, but the model's phrasing this run ("does not explicitly mention...") dropped the inline citation tag on an otherwise reasonable answer. Prompt-adherence variance (see original "Citation format has three distinct outcomes" observation above), not an embedding regression. |
| `gq-012` | multi_hop, narrative (no table) | `ok` → `ok` | Comparable outcome; reasonably grounded with citations. |
| `gq-019` | year_collision, table_heavy, single_doc | `insufficient_evidence` → `insufficient_evidence` | Same failure mode as before — retrieval still surfaces "Comparative figures" footnotes across multiple years' financials instead of the statement of earnings. The `year_collision` gap is unaffected by task prefixing, as expected (it's a semantic-vs-literal ranking issue, not a document/query asymmetry issue). |
| `gq-003` | single_doc, table_heavy | `answer_uncited` → `answer_uncited` | Unchanged. |
| *(negative control)* | — | `insufficient_evidence` → `answer_uncited` | Retrieval distances for the off-topic query dropped from ≥1.01 to 0.87–0.91 — the absolute distance scale shifted with the new embedding space, as expected when prefixes change what's being compared. The model still correctly declined to answer ("There is no mention of the capital of France..."), it just phrased the decline without the classifier's expected "don't know"/"insufficient" keywords, so the `ask()` status classifier labels it `answer_uncited` instead of `insufficient_evidence`. Not a retrieval regression — the separation between on-topic (~0.55–0.65) and off-topic (~0.87–0.91) distances is still clearly present in the new scale. |

**Takeaway:** No evidence of a retrieval regression from adding task prefixes — the two
substantive gaps already on record (gq-001's year-span join, gq-019's `year_collision` literal
match) reproduce identically. The `status` deltas above are `ok`/`insufficient_evidence` →
`answer_uncited` label changes driven by `llama3.1`'s citation-phrasing variance and the
classifier's keyword matching against the shifted distance scale, not by worse retrieval. This is
the same "three distinct outcomes" prompt-adherence gap flagged in the original run, not a new
issue introduced by this change. Because both `_embed_documents()` and `_embed_query()` now
apply prefixes consistently and the whole collection was rebuilt from scratch (no mixed-scheme
vectors), the prefixing itself is working as designed per `specs/naive-rag/spec.md`.

## 2026-08-24 addendum — rigorous prefix vs. no-prefix retrieval diff

The comparison above judged the prefix change by eyeballing the raw distance-value ranges before
and after (e.g. "0.545–0.606" looking broadly similar to the old "0.27–0.63" band), which is weak
evidence — Chroma's collection here has no `hnsw:space` metadata set, so it defaults to squared
L2 over nomic-embed-text's unit-normalized vectors (verified directly: `distance == 2 - 2·cos_sim`
for a known pair). Absolute distance scale is a property of the metric/model, not a direct proxy
for whether prefixing changed *which* chunks get retrieved.

To get a real answer, two things were verified directly against the live index and a freshly
built throwaway unprefixed index (same 1147 child chunks, same embedding calls, prefix stripped
to replicate pre-change behavior):

- **The live index is genuinely prefixed, not stale.** A vector pulled directly from the live
  collection matches a fresh re-embed of that chunk's text with the `search_document: ` prefix
  almost exactly (L2 ≈ 2×10⁻⁸) and is far from an unprefixed re-embed of the same text (L2 ≈
  0.44). The reindex took effect.
- **The prefix meaningfully changes the embedding vectors.** Plain vs. `search_document:`- vs.
  `search_query:`-prefixed encodings of the same string differ by L2 ≈ 0.26–0.50 — larger than the
  entire on-topic/off-topic distance band in retrieval results. This is not a no-op.

With that settled, the two indexes' `retrieve()` top-6 were diffed chunk-by-chunk for the same
golden subset plus the negative control:

| id | top-6 chunk_id overlap (Jaccard) | notes |
|---|---|---|
| `gq-001` | 0.71 (5/6 same) | Same 2020–2022 evidence set in both, reordered only. 2023 still absent either way — confirms the "same substantive gap" claim above was accurate, not just asserted. |
| `gq-002` | 0.71 (5/6 same) | Reordering only. |
| `gq-003` | 0.71 (5/6 same) | Reordering only. |
| `gq-005` | 0.71 (5/6 same) | Reordering only. |
| `gq-012` | 0.50 (4/6 same) | **Real evidence swap, not just reordering.** Prefixing drops both 2021-specific chunks in favor of unrelated 2020/2022 content, for a question explicitly asking to compare 2021 vs. 2023 — a plausible quality regression on this item specifically. |
| `gq-019` | 1.00 (identical set) | No change at all. |
| *(negative control)* | 0.09 (1/6 same) | Expected — an irrelevant query has no real signal, so which noise floats to the top is arbitrary under either scheme. |

Mean Jaccard across the 6 golden questions is ~0.68 (0.64 including the negative control) — i.e.
roughly a third of retrieved evidence changed on average, more churn than "distances look similar"
suggested. The on-topic/off-topic separation margin also *shrank* under prefixing rather than
widening: unprefixed on-topic max (~0.73) vs. off-topic min (~1.02) is a gap of ~0.29; prefixed
on-topic max (~0.70) vs. off-topic min (~0.87) is a gap of ~0.17. By that measure, discrimination
between relevant and irrelevant evidence got tighter, not better.

**Revised takeaway:** the prefix change is mechanically correct (verified independently of any
distance-scale reasoning) and mostly neutral for this golden subset — five of six questions kept
the same candidate evidence, just reordered. But "no evidence of regression" above overstates it:
gq-012 lost real 2021-side evidence, and the on-topic/off-topic distance margin narrowed. This
isn't a case for reverting the prefix change (it's the behavior nomic-embed-text was trained for,
and the literal-vs-semantic `year_collision` failure mode it was hoped to help with is unrelated
to it, as already noted), but it's not the unambiguous improvement the original framing implied
either — worth a real eval-set comparison (precision/recall against golden citations, not just
distance-scale or single-item spot checks) before leaning on task prefixing as a fix for anything
beyond matching nomic-embed-text's documented usage.

## 2026-08-27 addendum — corrected corpus (`strip-page-furniture`, task 6.4)

**Status:** RUN — local Ollama (`llama3.1`, `nomic-embed-text`) reachable; index rebuilt from
scratch via `hfx-index --reset --v1-batch` after `corpus/parsed/*` and `corpus/chunks/*` were
regenerated with `openspec/changes/strip-page-furniture`'s fused furniture-detection signal
(`parse.py`) and running-header/subtext fold (`chunk.py`). **The numbers below are not directly
comparable to either run above** — the child-chunk population itself changed (1147 → 983, a
14.3% reduction from stripping degenerate furniture-only chunks and merging previously-fragmented
parents), not just the embedding scheme, so retrieval indices and chunk_ids differ structurally,
not just by ranking. Same golden subset used in the two runs above (`gq-001/002/003/005/012/019`
plus the negative control), still task-prefixed per the `nomic-embed-task-prefixes` change (both
changes are cumulative on `main`, not alternatives).

| id | tags | status (2026-08-24 → 2026-08-27) | notes |
|---|---|---|---|
| `gq-001` | yoy_metric, multi_hop, narrative, table_heavy (flagship) | `answer_uncited` → `answer_uncited` | Unchanged. Retrieval still tops out around 2020–2023 mixed evidence without a clean year-span join; still the expected Phase 1 ceiling per design.md, not a furniture-fix regression. |
| `gq-002` | single_doc, narrative | `answer_uncited` → `ok` | Flipped back to `ok` — consistent with the citation-format prompt-adherence variance already on record (three prior instances of this same flip direction), not attributable to the corpus fix. |
| `gq-003` | single_doc, table_heavy | `answer_uncited` → `answer_uncited` | Status unchanged, but retrieval composition changed: this run's top-6 include the *correct* `2023_financials_en` "Consolidated statement of earnings" chunk (previously buried behind uncited auditor's-responsibilities boilerplate), alongside a `2022_financials_en` statement-of-earnings chunk. The model's prose leaned on the 2022-vs-2021 comparative figures ($13,815/$13,151) rather than the 2023-vs-2022 figures ($13,841/$13,815) the question asks for, despite both being retrieved — an answer-composition issue (which retrieved statement the model chose to summarize), not a retrieval miss. Worth a closer look if `gq-003` keeps landing on the wrong year's statement in future runs. |
| `gq-005` | single_doc, narrative, table_heavy | `ok` → `ok` | Unchanged. |
| `gq-012` | multi_hop, narrative (no table) | `ok` → `ok` | Status unchanged; substance unchanged too — 2021-side evidence is still thin relative to 2022/2023 (only 1 of 6 top hits is `2021_annual_en`, vs. 3 `2023_annual_en` and 1 `2022_annual_en`). The furniture fix did **not** resolve the evidence-swap behavior flagged in the 2026-08-24 addendum — see Open Question answer below. |
| `gq-019` | year_collision, table_heavy, single_doc | `insufficient_evidence` → `insufficient_evidence` | Status unchanged, and the failure mode is identical: all 6 top hits are still "17./16. Comparative figures" footnote sections, one per financials report (2020–2023), rather than the "Consolidated statement of earnings" section the question needs. Furniture contamination is not what was causing this miss — see Open Question answer below. |
| *(negative control)* | — | `answer_uncited` → `insufficient_evidence` | Flipped back to the "clean" label — same prompt-adherence variance as `gq-002`, not a retrieval signal. Distance separation is, if anything, slightly wider than the 2026-08-24 run's prefixed band (on-topic max ~0.63 vs. off-topic min ~0.87, a gap of ~0.24 vs. that run's ~0.17). |

**Answering design.md's Open Question** ("Does fixing the structural fragmentation measurably
change `gq-019`'s `year_collision` outcome or `gq-012`'s evidence-swap behavior?"): **No, not on
this golden subset.** Both failure modes reproduce identically post-fix:

- `gq-019`'s retrieval still ranks the literal phrase "Comparative figures" (present verbatim as
  a heading in every financials report's footnote 16/17, unrelated to the actual statement of
  earnings) above the semantically-correct section. This was always a lexical-vs-semantic ranking
  problem in the embedding/retrieval layer, not a furniture-contamination problem — the furniture
  fix improves what's *inside* chunks and how sections are bounded, but doesn't touch which
  section text ranks highest for a given query embedding. Confirms the Open Question's implicit
  suspicion that these are separate problems requiring separate fixes (year_collision needs
  something like `typed-retrieval-tools`'s section-type classifier, not a corpus-quality pass).
- `gq-012`'s 2021-vs-2023 comparison still retrieves mostly 2022/2023 evidence with thin 2021
  coverage. Same reasoning: furniture stripping reduces noise within chunks, it doesn't rebalance
  which report-year a similarity search favors for a given query.

**Corpus-quality impact, for context** (not itself an eval-quality claim): total child chunks
983 vs. 1147 before (-14.3%), and boilerplate contamination of child chunks fell from 14.4% to
1.5% corpus-wide (`tasks.md` 5.2). That improvement is real and measured, but — per the answer
above — it addresses a different axis of corpus quality than the two ranking failures this golden
subset's `year_collision`/multi-hop tags were designed to surface. Both remain open for whichever
Phase 2 change (`typed-retrieval-tools`, `langgraph-plan-critique-loop`) picks them up next.

## 2026-08-31 pointer — `typed-retrieval-tools` follow-up

Both failure modes flagged above (`gq-001`'s missing-2023 year-span join, `gq-019`'s
`year_collision` footnote ranking) are now addressed at the retrieval layer, decoupled from
`ask()`: see `evals/typed_retrieval_validation.md` for the full direct-call coverage results
(per-year fan-out closes the year-crowding gap; section-type re-ranking avoids the footnote
collision on both `gq-019` and `gq-020`). This golden-subset baseline document remains the
record of naive `retrieve()`/`ask()` behavior; it is intentionally left unmodified otherwise.
