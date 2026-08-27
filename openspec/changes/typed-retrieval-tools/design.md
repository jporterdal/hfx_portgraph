## Context

`rag.py`'s `retrieve()` embeds the question once and runs a single `collection.query()` against the whole Chroma collection — no `where` filtering, even though every indexed child already carries `year`, `report_id`, `section`, and `heading` metadata (`rag.py::index_reports`). That single global top-k ranking is why `gq-001` (2020–2023 operating income + throughput) surfaced 2020–2022 evidence and dropped 2023 entirely: nothing forces per-year representation, so whichever year's passages rank highest in raw similarity crowd out the rest. It's also why `gq-019` (`year_collision`) matched a "17. Comparative figures" footnote across all four financials docs instead of the actual statement of earnings section — literal phrase overlap beats semantic section targeting when there's no way to prefer one section over another.

This change builds the typed retrieval layer `phase-1-parse-rag/design.md` earmarked for Phase 2 ("Hand off retrieval substrate to Phase 2: LangGraph wraps same tools"), but builds it now, decoupled from any agent framework, so it's directly testable against `evals/golden.jsonl`'s existing `expected_evidence` (years/report_ids/metrics/entities per item) before `langgraph-plan-critique-loop` exists.

## Goals / Non-Goals

**Goals:**
- Typed retrieval functions (by year, by report, by section-type) that materially improve evidence coverage on `multi_hop`/`yoy_metric`/`year_collision`-tagged golden items when called directly (not through `ask()`).
- Zero changes to `corpus/parsed/`, `corpus/chunks/`, or `data/chroma/` — everything is built from metadata already indexed.
- Same hit shape as today's `retrieve()`, so `_format_context()` and any future tool wrapper work unmodified.
- A validation pass that gives Phase 2's planner design real numbers on what typed, multi-call retrieval can and can't fix on its own.

**Non-Goals:**
- No LangGraph/LangChain `@tool` binding — this change ships plain Python functions; framework adapters are `langgraph-plan-critique-loop`'s job.
- No changes to `ask()`, `cli.py`, or Phase 1's naive-RAG CLI behavior.
- No fix for the `answer_uncited` citation-format prompt-adherence gap (`gq-003`) — that's generation-layer, owned by the synthesizer work in the next change.
- No RAGAS/LLM-as-judge scoring harness — validation stays qualitative/coverage-based, matching Phase 1's existing eval posture.
- No new metadata fields requiring re-indexing (see Decision 2).

## Decisions

**1. Per-year fan-out querying, not a single filtered top-k, for multi-year coverage.**
For a request spanning N years, run N separate Chroma queries — same query embedding, each with a `where={"year": {"$eq": y}}` filter — and take the top-k *per year*, rather than one query with `where={"year": {"$in": years}}` and a larger top-k. A single large-top-k query still lets years with more/denser matching passages crowd out thinner years (exactly today's `gq-001` failure); per-year fan-out guarantees every requested year gets a chance to surface its own best evidence.
- *Alternative considered:* one query with `$in` filter and `n_results = k * len(years)`, then check for per-year gaps and backfill. Rejected as the default because it still lets one year's passages dominate the ranked list before any gap-check runs; kept available as a cheaper coarse mode when the caller doesn't need a coverage guarantee (e.g. a single-year lookup).
- Cost mitigation: embed the question text once and reuse the same embedding vector across all N fan-out calls — only the `where` filter changes per call, so this doesn't multiply Ollama embed calls, only Chroma queries (cheap, local).

**2. Filter on existing metadata only; derive `report_type` rather than re-indexing.**
`year`, `report_id`, `section`, `heading` are already stored per child. `report_type` (annual vs. financials) is not currently indexed. Rather than add it as a new metadata field (which would require re-indexing all 1147 children), derive it by cross-referencing the requested `report_id`(s) against `corpus/manifest.yaml`'s existing `report_type` field per entry — the manifest is already the source of truth for report identity, so this avoids both a schema change and a fragile string-parsing convention on `report_id`.

**3. Section-type classification happens in Python, after retrieval, not as a Chroma `where` clause.**
Chroma's `where` only supports exact/comparison matches on stored metadata — it can't regex-match or pattern-classify `heading` text. So "is this a footnote/note section or a primary statement section" is computed at query time from the already-stored `heading`/`section` string via a small heuristic (numbered-note pattern like `^\d+\.\s`, vs. keyword pattern like "Statement of" / "Consolidated statement of"), applied as a post-query filter/re-rank step in Python. This is a *re-ranking signal*, not a hard exclude: heuristic misses are expected and get logged in the validation note rather than silently dropping evidence a caller might still need.

**4. Uniform hit shape; no new data model.**
Every typed function returns the same dict shape `retrieve()` already returns: `chunk_id`, `text`, `distance`, `metadata`, `parent_text`. `_format_context()` and any Phase 2 tool wrapper consume typed and naive hits identically.

**5. Plain functions now, framework binding later.**
Ship `retrieve_by_year()`, `retrieve_by_report()`, `retrieve_with_section_filter()` etc. as importable Python functions with clear signatures — no LangChain/LangGraph dependency added in this change. `langgraph-plan-critique-loop` wraps these as typed tools once the graph's tool-calling convention is settled; keeping the binding out of this change means it stays testable with a plain script/pytest against the golden set.

**6. Validation is a direct-call coverage check against `expected_evidence`, not a full eval harness.**
A small script exercises the new functions directly (bypassing `ask()`/the LLM entirely) against every `multi_hop`, `yoy_metric`, and `year_collision`-tagged golden item: for each, does per-year fan-out return ≥1 hit for every year in `expected_evidence.years`? Does section-filtered retrieval for the `year_collision` items exclude the footnote section that beat the correct one in `phase1_baseline.md`? Results go in `evals/typed_retrieval_validation.md`. This is deliberately not RAGAS/LLM-judge scoring (an explicit Phase 1 non-goal that still applies) — it's a mechanical coverage check, not answer-quality scoring.

## Risks / Trade-offs

- **[Risk] Per-year fan-out multiplies Chroma query calls** (one per requested year) → for a 7-report, 4-year query that's 4 Chroma calls instead of 1. **Mitigation:** Chroma queries are local and cheap; only the embedding call (the actually-costly Ollama round trip) is shared across all fan-out calls.
- **[Risk] `report_type` derivation depends on `corpus/manifest.yaml` staying authoritative** → if a caller passes a `report_id` not present in the manifest, type derivation fails. **Mitigation:** raise a clear error rather than guessing from the id string; the manifest's `report_type` field is already required reading elsewhere in the pipeline (`paths.py::v1_present_reports`).
- **[Risk] Section-type heuristic will misclassify some headings** (footnote vs. statement is a fuzzy boundary in real annual-report ToCs) → could deprioritize a legitimately relevant footnote or fail to catch a new collision pattern. **Mitigation:** re-ranking signal, not a hard filter; document known misses in `evals/typed_retrieval_validation.md` instead of treating the heuristic as ground truth.
- **[Trade-off] No tool-framework binding yet** → `langgraph-plan-critique-loop` has to write a thin adapter layer before these are callable as LangGraph tools. Accepted: keeps this change's dependency footprint at zero and makes the functions testable in isolation now, which was the point of splitting Phase 2 this way.

## Open Questions

- Should per-year fan-out's per-year top-k be fixed (e.g. `k=3` per year) or scale with the number of years requested to keep total context bounded for a wide year-span question? Leaning toward a fixed small per-year `k` with an overall cap, decided during implementation against `gq-001`'s actual context-window behavior.
- Does the section-type heuristic need report-type awareness (financials footnote numbering vs. annual report dashboard sections look different) or is one pattern set good enough for the v1 8-report corpus? To be settled by what `evals/typed_retrieval_validation.md` actually shows on `gq-019`/`gq-020`.
- **Resolved by sequencing, not by decision here:** `strip-page-furniture/design.md`'s Open Questions flagged a risk that this change's Decision 3 section-type classifier is keyed entirely on each chunk's `heading`/`section` metadata — the exact field `strip-page-furniture`'s Point 1 (furniture-as-heading) was corrupting for ~10-19% of chunks pre-fix. That change has since landed (`corpus/parsed/*`/`corpus/chunks/*` regenerated, `data/chroma` reindexed, `evals/phase1_baseline.md`'s 2026-08-27 addendum) *before* this change's implementation started (`tasks.md` still 0/15 as of that addendum), so the section-type classifier will be built and validated against clean heading metadata from the start, as `strip-page-furniture` recommended — no re-validation debt inherited. One relevant data point carried over: that addendum re-ran `gq-019` post-fix and found its `year_collision` failure mode (retrieval ranking "Comparative figures" footnote headings above the real "Consolidated statement of earnings" section) reproduced identically — confirming it's a ranking-layer problem this change's section-type classifier is still the right tool for, not something the furniture fix already solved.
- **Possible feature source, not yet designed:** `strip-page-furniture/design.md`'s "Known intentional gap" section (added after the addendum above) documents that `gq-019`'s colliding "Comparative figures" chunks are near-verbatim boilerplate repeated once per report across 6 of 8 reports — deliberately left unstripped, because cross-document boilerplate similarity is itself informative (same phrasing across reports implies the same disclosure/note type), not noise. That's a candidate positive signal for this change's section-type heuristic (e.g. "this chunk's text is near-duplicate of a chunk in another report's same-numbered note" as a same-type-of-note feature) rather than something the classifier needs to fight through. Not scoped into Decision 3 as written; worth a look if the heuristic's initial precision on `gq-019`-style collisions falls short of `evals/typed_retrieval_validation.md`'s bar.
