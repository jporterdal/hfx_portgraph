## 1. Setup

- [x] 1.1 Add `langgraph` (pinned version range) to `pyproject.toml` dependencies
- [x] 1.2 Create `hfx_portgraph/agent.py` (or `agent/` subpackage) with the state schema: question, plan, evidence-by-goal, sufficiency gaps, iteration count, max_iterations, final answer/citations

## 2. Planner node

- [x] 2.1 Write the planner prompt: decompose the question into `{years, report_ids, metrics, entities}`, no retrieval, structured JSON output
- [x] 2.2 Implement lenient JSON extraction from the model response (first well-formed `{...}` block)
- [x] 2.3 Implement the retry-once-then-fallback path: on parse failure, retry with a stricter "JSON only" instruction; on second failure, fall back to a single evidence goal covering the whole question
- [x] 2.4 Unit-test the planner directly against a handful of `evals/golden.jsonl` items, comparing produced plans to each item's own `expected_evidence`

## 3. Retriever node

- [x] 3.1 Implement dispatch logic mapping plan evidence goals to `typed-retrieval-tools` calls (`retrieve_by_year`, `retrieve_by_report`, `retrieve_with_section_filter`), joining metric/entity text into the query string per call. **[2026-08-31, resolved]** For entity/metric-only goals with no year (dispatched via bare `retrieve_by_report`, per design.md Decision 4), `typed-retrieval-tools/design.md`'s Decision 7 (fan-out `retrieve_by_report` by default) has landed — `retrieve_by_report` now guarantees per-report_id coverage on the bare call, so this dispatch path can be implemented directly against it (see `evals/typed_retrieval_validation.md`'s report-axis comparison table). **[2026-10-14, as implemented]** All units dispatch through `retrieve_with_section_filter()`, one year or one report_id per unit, rather than calling `retrieve_by_year`/`retrieve_by_report` directly — see design.md Decision 4 amendments
- [x] 3.2 Implement the per-iteration dispatch ceiling, prioritizing one call per planned year over exhaustive year×metric pairing when the plan would exceed it
- [x] 3.3 Accumulate retrieved hits into state, keyed by the evidence goal they satisfy, without duplicating identical chunk ids already accumulated in a prior iteration

## 4. Critic node

- [x] 4.1 Implement coverage checking: for each planned year (and report id where applicable), does accumulated evidence include at least one matching hit
- [x] 4.2 Implement the bounded-retry decision: request a focused retrieval pass for missing slots only, incrementing iteration count, up to `max_iterations`
- [x] 4.3 Implement the iteration-cap exit: once `max_iterations` is reached, proceed to synthesis and record remaining gaps in state rather than looping further

## 5. Synthesizer node

- [x] 5.1 Assemble the final-answer prompt from all accumulated evidence across evidence goals, reusing/adapting `rag.py::_format_context()` for context formatting. **[2026-10-14, as implemented]** Evidence is capped per slot and overall, with `num_ctx` sized to the prompt — see design.md Decision 9
- [x] 5.2 Instruct the model to explicitly state "no evidence found" for any plan goal recorded as an uncovered gap, rather than omitting it or inventing a value
- [x] 5.3 Implement citation-tag detection (reusing `ask()`'s `"chunk_id=" in answer.lower()` check) and the one-shot repair re-prompt when citations are missing but evidence was supplied
- [x] 5.4 Assemble the final result dict matching `ask()`'s shape (`question`, `status`, `answer`, `citations`, `hits`) plus new `plan` and `iterations` fields

## 6. Graph wiring and entrypoint

- [x] 6.1 Wire planner → retriever → critic → (loop or synthesizer) as a LangGraph state machine
- [x] 6.2 Add a new CLI entrypoint (e.g. `hfx-agent-ask`) in `cli.py` and register it in `pyproject.toml`'s `[project.scripts]`, mirroring `ask_main`'s argument shape where reasonable
- [x] 6.3 Smoke-test the full graph against `gq-002` (single_doc, low-risk) before running multi-hop items

## 7. Golden-set validation and baseline

- [x] 7.1 Run `gq-001` (flagship) through the new agent; confirm evidence coverage across all requested years (2020–2023) compared against `phase1_baseline.md`'s "missed 2023 entirely" result
- [x] 7.2 Run the remaining `multi_hop`/`yoy_metric`-tagged items (`gq-004`, `gq-007`, `gq-010`, `gq-012`, `gq-014`, `gq-017`, `gq-022`, `gq-024`, `gq-025`) and the `year_collision`-tagged items (`gq-019`, `gq-020`) through the agent
- [x] 7.3 Re-run `gq-003` specifically to confirm the citation-repair path resolves the `answer_uncited` outcome recorded in `phase1_baseline.md`
- [x] 7.4 Write `evals/phase2_baseline.md` with per-item outcomes, directly comparable to `evals/phase1_baseline.md`'s table format

## 8. Wrap-up

- [x] 8.1 Confirm no changes were made to `corpus/parsed/`, `corpus/chunks/`, `data/chroma/`, `rag.py`, or the existing `hfx-ask` CLI (this change is additive only)
- [x] 8.2 Add a Phase 2 follow-on note to `docs/phase-1.md` and update `PLAN.md`'s phase table to reflect Phase 2 as shipped

## 9. Plan-keyed evidence (design.md Decision 5 amendment, 2026-10-14)

- [x] 9.1 Carry each dispatch unit's plan-slot key (`year:Y` / `report:R`) through dispatch in `retriever_node`, and accumulate hits into evidence under that key rather than flattening hits and re-deriving the key from metadata
- [x] 9.2 Remove `_slot_key_for_hit` (or narrow it to a documented fallback, if any caller still needs one) so the evidence key space matches `_plan_slots` by construction
- [x] 9.3 Verify with a report-only plan (`report_ids` set, `years` empty): report slots register as covered after one pass, no retry is issued, and no false gap notice reaches the synthesizer
- [ ] 9.4 Re-run at least one year-plan golden item (e.g. `gq-001`) and confirm unchanged evidence keys, iterations, and status versus `evals/phase2_baseline.md`

## 10. Hard dispatch ceiling (design.md Decision 4 amendment, 2026-10-14)

- [x] 10.1 In `build_dispatch_units`, cap the collapsed one-unit-per-year path at `ceiling` units (first `ceiling` years, ascending), matching the existing cap on the report path, so no pass ever exceeds the ceiling
- [x] 10.2 Add a short comment at the cap noting the known limitation (years beyond `ceiling × max_iterations` are unreachable) and pointing to design.md Decision 4
- [x] 10.3 Verify with a synthetic plan whose year count exceeds a small ceiling (e.g. 6 years, `dispatch_ceiling=4`): first pass issues 4 calls, the 2 undispatched years appear as critic gaps, and the retry pass dispatches them
