## Why

`rag.py`'s `retrieve()` does one undifferentiated similarity search per question — no way to target a specific year, report, or section type. `evals/phase1_baseline.md` shows exactly where this breaks: `gq-001` (the flagship multi-year query) missed 2023 entirely because nothing forces the retriever to cover every year in span; `gq-019` matched the wrong section ("17. Comparative figures" footnote) across all four financials docs because literal-phrase similarity beat semantic section targeting — the `year_collision` failure mode by design. `phase-1-parse-rag/design.md` already planned for this: *"Hand off retrieval substrate to Phase 2 (LangGraph wraps same tools)."* Phase 2's planner/critic loop needs typed retrieval primitives to call — by year, by report, by metric/entity keyword, by section type — rather than one bare similarity search. Building these now, decoupled from any LangGraph state machine, means they can be validated directly against `evals/golden.jsonl`'s existing `expected_evidence` (years/report_ids/metrics/entities are already encoded per item) before any agent-loop code exists, and Phase 2 can consume a settled tool contract instead of building it inline.

## What Changes

- Add typed retrieval functions wrapping the existing Chroma collection with metadata `where` filters (currently unused): `retrieve_by_year(years, ...)`, `retrieve_by_report(report_ids, ...)`, and a combined filter form so callers can constrain year + report + section together.
- Add a metric/entity-oriented retrieval path that combines a keyword/semantic query against child text with the metadata filters above, so a caller can ask for "operating income across 2020–2023" as a set of typed calls rather than one query string.
- Add section-type-aware retrieval (e.g. distinguishing primary statement sections from notes/footnote sections using heading/section metadata) to address the literal-phrase collision seen in `gq-019`.
- Each typed function returns the same hit shape `retrieve()` already produces (chunk_id, text, metadata, parent_text) so downstream consumers (today's `ask()`, tomorrow's LangGraph tool wrappers) don't need a second data shape.
- Add a standalone validation pass that exercises the new typed functions directly (not through `ask()`) against `evals/golden.jsonl`'s `expected_evidence` for the `multi_hop`/`yoy_metric`/`year_collision`-tagged items, and records whether typed, multi-call retrieval can actually surface full evidence coverage (e.g. all 4 years for `gq-001`) — the answer feeds directly into Phase 2's planner design.
- Existing `retrieve()` and `ask()` are left unchanged; this change is additive, sitting alongside the Phase 1 naive-RAG path rather than replacing it. Phase 1's single-shot `ask()` remains the CLI-facing behavior until Phase 2's planner/critic loop supersedes it.

## Capabilities

### New Capabilities
- `typed-retrieval-tools`: year-, report-, section-type-, and metric/entity-filtered retrieval functions over the existing Chroma child-chunk index, returning the same hit shape as naive retrieval, validated against golden-set expected evidence coverage.

### Modified Capabilities
(none — `naive-rag`'s `retrieve()`/`ask()` behavior and requirements are unchanged; typed tools are a new, additive interface that Phase 2 will consume, not a replacement for the existing naive-RAG path.)

## Impact

- **New code**: typed retrieval functions in `hfx_portgraph/rag.py` (or a new `hfx_portgraph/retrieval_tools.py` module) using Chroma's `where` metadata filtering (`year`, `report_id`, `section`/`heading`), which the collection already stores per child chunk but nothing currently queries against.
- **New eval artifact**: a validation note (e.g. `evals/typed_retrieval_validation.md`) documenting golden-set evidence-coverage results for the new typed functions, feeding Phase 2's `langgraph-plan-critique-loop` design.
- **No changes** to `corpus/parsed/`, `corpus/chunks/`, or `data/chroma/` artifacts or schemas — the metadata fields being filtered on (`year`, `report_id`, `section`, `heading`, `page_start`/`page_end`) already exist on every indexed child chunk; no re-parsing, re-chunking, or re-indexing required.
- **No changes** to `ask()`, `cli.py`'s `ask_main`, or CLI-facing behavior — Phase 1's naive-RAG surface is untouched; the answer-citation prompt-adherence gap (`answer_uncited` on `gq-003`) stays with the synthesizer work in the upcoming `langgraph-plan-critique-loop` change, since it's a generation-layer concern, not a retrieval one.
- **Downstream**: `langgraph-plan-critique-loop` (the next change) imports these typed functions as its retriever-node tools rather than building retrieval logic inline.
