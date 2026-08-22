## Context

`typed-retrieval-tools` (implemented ahead of this change) gave the project `retrieve_by_year()`, `retrieve_by_report()`, and `retrieve_with_section_filter()` — all plain Python functions, deliberately not bound to any agent framework, returning the same hit shape as `rag.py::retrieve()`. What's still missing is the thing that decides *when* to call which one: `gq-001` needs four `retrieve_by_year()` calls (one per 2020–2023) plus a metric-shaped query text for each, not one. Nothing today decomposes a question into that plan, checks whether the results actually cover it, or knows when to stop trying. That's this change's job, and it's the entire scope PLAN.md reserves for Phase 2: *"plan → retrieve → critique → answer (no Neo4j yet)."*

`PLAN.md` already locked three design decisions this change must honor: (1) typed retrieval tools over free-form queries from a small model — already satisfied by `typed-retrieval-tools`; (2) max loop count + explicit insufficiency, not unbounded iteration; (3) every claim cites chunk/page. `llama3.1` (8B, local, via Ollama) is the only model available — its structured-output reliability is a known constraint (`PLAN.md`: *"Extraction quality with Llama 3.1 8B will be the bottleneck"*), which shapes several decisions below.

## Goals / Non-Goals

**Goals:**
- A bounded-iteration LangGraph loop (planner → retriever → critic → synthesizer) that materially improves on Phase 1's naive-RAG outcomes for `gq-001` and the other `multi_hop`/`yoy_metric`-tagged golden items.
- Deterministic, code-driven dispatch of typed retrieval calls from a structured plan — not LLM tool-calling — to avoid depending on `llama3.1`'s function-calling reliability.
- A citation-repair path in the synthesizer that directly addresses the `answer_uncited` gap (`gq-003`) instead of just detecting it.
- `evals/phase2_baseline.md`, directly comparable to `evals/phase1_baseline.md`, as the concrete exit signal.

**Non-Goals:**
- No Neo4j, ontology, or typed Cypher tools (Phase 3).
- No RAGAS / LLM-as-judge scoring — critic coverage checking is mechanical (presence of evidence per planned slot), not a semantic-correctness judge; answer-quality assessment stays qualitative, matching Phase 1's posture.
- No report compiler / multi-section research UX (Phase 4).
- No changes to `rag.py`'s `ask()`/`retrieve()` or the `hfx-ask` CLI — this ships as a new, additive entrypoint.
- No fixed metric/entity ontology — the planner emits free-text metric/entity phrases; enforcing a real ontology is Phase 3's job.

## Decisions

**1. Deterministic Python dispatch for retrieval, not LLM tool-calling.**
The planner emits a structured plan (JSON); the retriever *node* is ordinary Python that reads the plan and calls `typed-retrieval-tools` functions directly — the LLM never invokes a tool-calling API. This mirrors `PLAN.md`'s own principle for the later Neo4j phase ("prefer typed tools ... over free-form Cypher from a small model") applied one phase early: an 8B local model is more reliable at producing a small JSON object than at driving a tool-calling loop correctly every time, and deterministic dispatch means a malformed plan degrades gracefully (see Decision 3) instead of the whole turn failing.
- *Alternative considered:* LangGraph's native tool-calling (model emits tool calls, graph executes them). Rejected for now given `llama3.1` 8B's structured-output reliability is already flagged as a project risk; revisit if a larger local model becomes available.

**2. Plan shape mirrors `evals/golden.jsonl`'s `expected_evidence`.**
The planner's structured output is `{"years": [...], "report_ids": [...], "metrics": [...], "entities": [...]}` — the same fields `evals/golden.jsonl` already uses per item. This isn't a coincidence: the golden set's evidence shape *is* the target decomposition shape, so golden items double as planner test cases (does the planner reconstruct something close to the item's own `expected_evidence`?) without needing new fixtures.

**3. Lenient JSON parsing with a safe single-goal fallback, never a hard failure.**
Planner and critic outputs are parsed leniently (extract the first well-formed `{...}` block from the model's response). On a parse failure, retry once with a stricter "respond with ONLY a JSON object" instruction; if that also fails, fall back to a single evidence goal treating the whole question as one metric/entity query with no year/report constraint — i.e. degrade toward Phase 1's naive single-shot behavior rather than crashing the turn. This bounds the blast radius of the known `llama3.1` structured-output risk.

**4. Retriever dispatch is capped, not a full cross-product.**
For a plan with Y years and M metrics, naively dispatching one typed call per (year, metric) pair could mean Y×M Chroma queries. Cap total dispatch calls per iteration at a fixed ceiling (e.g. 12); when the plan would exceed it, prioritize covering every year at least once (one call per year, metric text joined into a single query string) over exhaustively covering every year×metric pair. Metric- or entity-only goals with no year (e.g. `gq-001`'s "strategic initiatives") dispatch via `retrieve_by_report()` scoped to the plan's `report_ids` (or all v1 reports if unspecified), without a year filter.

**5. Critic checks evidence *presence* per planned slot, not semantic correctness.**
For each planned year (and, where feasible, each planned report_id), the critic checks whether accumulated evidence includes at least one hit whose metadata matches that slot. This is a mechanical coverage check, not a judgment of whether the retrieved passage actually answers the question — real answer-quality assessment is explicitly out of scope (no LLM-as-judge, matching Phase 1's non-goals). If any planned year is missing evidence, the critic loops back requesting retrieval focused on just the missing slots (not a full re-plan), bounded by `max_iterations`.

**6. Max iterations defaults to 2, with per-slot partial insufficiency rather than all-or-nothing.**
After `max_iterations` is exhausted, synthesis proceeds with whatever evidence exists. Slots still missing evidence are passed to the synthesizer as explicit gaps, and the synthesizer is instructed to state "no evidence found for <year/metric>" for those specific slots rather than silently omitting them or refusing the entire answer — matching Phase 1's "no invented numbers" rule while still returning a partial, cited answer for the slots that *were* covered (an improvement over Phase 1's binary ok/insufficient_evidence outcome for a question like `gq-001` that's answerable for some years but not others).

**7. Synthesizer includes a bounded citation-repair retry.**
After the LLM produces an answer, run the same `"chunk_id=" in answer.lower()` check `ask()` already uses. If citations are missing but evidence was supplied, re-prompt once with the same evidence and a stronger citation-format reminder before falling back to `answer_uncited` status — a direct fix attempt for the exact failure `gq-003` exhibited, rather than only detecting it as `ask()` does today.

**8. New CLI entrypoint, output shape compatible with `ask()`.**
`hfx-agent-ask` (backed by a new `hfx_portgraph/agent.py`) returns the same top-level keys `ask()` does (`question`, `status`, `answer`, `citations`, `hits`) plus new `plan` and `iterations` fields, so `evals/phase2_baseline.md`'s tooling can reuse `phase1_baseline.md`'s comparison approach with minimal changes.

## Risks / Trade-offs

- **[Risk] `llama3.1` may produce malformed or incomplete JSON for planning/critique** → **Mitigation:** lenient parsing, one retry, safe single-goal fallback (Decision 3); never crashes the turn.
- **[Risk] Year×metric cross-product could multiply retrieval calls and latency for broad questions** → **Mitigation:** capped dispatch ceiling, year-coverage prioritized over exhaustive pairing (Decision 4).
- **[Risk] Critic's coverage check is presence-only, not correctness** → a "covered" slot could still hold irrelevant evidence. **Mitigation:** explicitly out of scope for this change (no LLM-judge); flagged for qualitative review the same way Phase 1's baseline was reviewed by hand.
- **[Risk] New dependency (`langgraph`) on a fast-moving package** → **Mitigation:** pin a version range in `pyproject.toml`; no other code depends on it yet, so a version bump later is low-blast-radius.
- **[Trade-off] Deterministic dispatch means the planner's JSON schema is a hard contract across planner prompt, parser, and retriever dispatch** → accepted: reliability with an 8B local model matters more than framework-idiomatic tool-calling at this stage; can migrate to native tool-calling later if a stronger model is swapped in.
- **[Trade-off] Partial-insufficiency answers (Decision 6) are more useful but more complex than Phase 1's binary status** → accepted given `gq-001`'s own shape (answerable for some years, not others) is exactly the case this change exists to handle better.

## Migration Plan

1. Add `langgraph` to `pyproject.toml` dependencies.
2. Implement and directly unit-test each node function (planner, retriever, critic, synthesizer) in isolation before wiring the graph, using a few golden items' `expected_evidence` as informal fixtures.
3. Wire the full graph; smoke-test against a low-risk `single_doc` item (`gq-002`) before the flagship `gq-001`.
4. Run the full `multi_hop`/`yoy_metric`/`year_collision`-tagged golden subset through `hfx-agent-ask`; write `evals/phase2_baseline.md` comparing per-item outcomes against `evals/phase1_baseline.md`.
5. Rollback: delete `hfx_portgraph/agent.py`, the new CLI script entry, and the `langgraph` dependency — no existing artifacts, indexes, or Phase 1 code paths are touched, so rollback is a pure code revert.

## Open Questions

- Is `max_iterations = 2` (Decision 6) the right default, or should it be 1 for cost/latency reasons given local Ollama inference speed? Decide empirically once `gq-001` timing is observed.
- Should the planner's metric/entity fields get a light suggested-vocabulary hint in the prompt (drawn from values already observed across `evals/golden.jsonl`) to improve JSON reliability, without hard-enforcing an enum? Leaning yes, deferred to implementation.
- Should `hfx-agent-ask` fully replace `hfx-ask` in day-to-day use once validated, or do both stay available indefinitely as a Phase 1 vs Phase 2 comparison pair? Leaning toward keeping both, at least through Phase 2's own eval-gate close-out.
