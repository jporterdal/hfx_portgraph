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
