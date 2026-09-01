## Why

`evals/phase1_baseline.md` confirms the Phase 1 ceiling by design: naive single-shot similarity retrieval cannot do the year-span join `gq-001` needs (it missed 2023 entirely), and even the typed retrieval primitives from `typed-retrieval-tools` (per-year fan-out, report-scoped, section-filtered) only fix retrieval *coverage* — nothing yet decides which years/metrics/entities to query for, checks whether what came back is actually sufficient before answering, or stops after a bounded number of tries instead of guessing. `PLAN.md`'s Phase 2 is exactly this gap: *"LangGraph: plan → retrieve → critique → answer (no Neo4j yet)."* `phase-1-parse-rag/design.md` scoped it out explicitly as a non-goal ("LangGraph plan/critique loops (Phase 2)") and flagged the multi-hop failure as expected, not a bug, deferring the fix to here. This change builds that loop now that its retrieval substrate (`typed-retrieval-tools`) exists to consume.

## What Changes

- Add `langgraph` as a new dependency (plus whatever minimal LangChain core types it requires for tool/message schemas — decided in design.md).
- Define an agent state schema carrying: the original question, a decomposed plan (evidence goals — years/metrics/entities/report_ids, shaped like `evals/golden.jsonl`'s existing `expected_evidence` fields), accumulated retrieved evidence per goal, a sufficiency verdict, iteration count, and the final cited answer.
- **Planner node**: decomposes the question into evidence goals via a constrained LLM call (`llama3.1` via Ollama) — no retrieval yet, matching `PLAN.md`'s planner role ("Decompose the question into evidence goals ... without retrieving").
- **Retriever node**: wraps `typed-retrieval-tools`' `retrieve_by_year`, `retrieve_by_report`, and `retrieve_with_section_filter` functions as callable tools, dispatching one or more typed calls per evidence goal and accumulating hits into state.
- **Critic node**: scores retrieved evidence against the plan (does every planned year/metric/entity have at least one hit?), and either loops back to refine the plan for missing slots or proceeds to synthesis — enforcing a max iteration count `N` with an explicit insufficiency exit, matching `PLAN.md`'s locked design decision ("Max loop N + explicit insufficiency").
- **Synthesizer node**: assembles the final answer from all accumulated evidence across evidence goals, replacing `ask()`'s single-shot citation formatting for this path. This is where the `answer_uncited` prompt-adherence gap (`gq-003`: right evidence, no citation tag) gets addressed — via structured citation validation/repair rather than trusting free-form model output, since that gap was explicitly deferred here from `typed-retrieval-tools`.
- New entrypoint (e.g. `hfx_portgraph/agent.py` + a new CLI script) alongside — not replacing — Phase 1's `hfx-ask`. `ask()`/`retrieve()` in `rag.py` remain untouched and available.
- Re-run the golden set's `multi_hop`/`yoy_metric`-tagged items (`gq-001`, `gq-004`, `gq-007`, `gq-010`, `gq-012`, `gq-014`, `gq-017`, `gq-022`, `gq-024`, `gq-025`) plus the `year_collision` items (`gq-019`, `gq-020`) through the new agent loop, and record results in a new `evals/phase2_baseline.md`, comparing directly against `evals/phase1_baseline.md`'s per-item outcomes — `gq-001` achieving full 2020–2023 coverage with citations is this change's concrete exit signal, per `evals/phase1_baseline.md`'s own framing.
- Explicit non-goals carried forward from `PLAN.md`: no Neo4j, no ontology/typed Cypher tools (Phase 3), no RAGAS/LLM-as-judge scoring harness, no report compiler (Phase 4).

## Capabilities

### New Capabilities
- `langgraph-plan-critique-loop`: a LangGraph state machine (planner → retriever → critic → synthesizer, bounded-iteration loop) that decomposes multi-hop questions into evidence goals, dispatches typed retrieval tool calls per goal, checks evidence sufficiency before answering, and produces a cited answer — addressing the Phase 1 naive-RAG ceiling on multi-year and year-collision questions.

### Modified Capabilities
(none — `naive-rag`'s `ask()`/`retrieve()` and `typed-retrieval-tools`' functions are consumed as-is, not changed. This change wraps them as LangGraph tools without altering their existing requirements or behavior.)

## Impact

- **New dependency**: `langgraph` (and any minimal supporting LangChain-core types needed for tool/message schemas — see design.md for the binding decision).
- **New code**: `hfx_portgraph/agent.py` (or an `agent/` subpackage) with the state schema and four graph nodes; a new CLI entrypoint (e.g. `hfx-agent-ask`) registered alongside `hfx-ask`.
- **New eval artifact**: `evals/phase2_baseline.md`, directly comparable to `evals/phase1_baseline.md`.
- **No changes** to `corpus/parsed/`, `corpus/chunks/`, `data/chroma/`, `rag.py`'s `ask()`/`retrieve()`, or the existing `hfx-ask` CLI — this change is additive, mirroring how `typed-retrieval-tools` was scoped.
- **Depends on** `typed-retrieval-tools` being implemented (not just proposed) — the retriever node imports `retrieve_by_year`, `retrieve_by_report`, and `retrieve_with_section_filter` directly; this change should not begin implementation until those functions exist and pass their own validation (`evals/typed_retrieval_validation.md`). **[2026-08-31, resolved]** That validation's original 7/10 report-coverage figure understated a real gap in bare (year-less) `retrieve_by_report` calls — exactly this change's Decision 4 dispatch shape for entity-only goals. `typed-retrieval-tools/design.md`'s Decision 7 amendment has since been implemented (report-coverage now 10/10 in the re-run validation); the dependency is fully satisfied.
- **Docs**: `docs/phase-1.md` gets a Phase 2 follow-on pointer once this lands; `PLAN.md`'s phase table moves from "pending" to shipped for row 2.
