## 1. Setup

- [ ] 1.1 Add `langgraph` (pinned version range) to `pyproject.toml` dependencies
- [ ] 1.2 Create `hfx_portgraph/agent.py` (or `agent/` subpackage) with the state schema: question, plan, evidence-by-goal, sufficiency gaps, iteration count, max_iterations, final answer/citations

## 2. Planner node

- [ ] 2.1 Write the planner prompt: decompose the question into `{years, report_ids, metrics, entities}`, no retrieval, structured JSON output
- [ ] 2.2 Implement lenient JSON extraction from the model response (first well-formed `{...}` block)
- [ ] 2.3 Implement the retry-once-then-fallback path: on parse failure, retry with a stricter "JSON only" instruction; on second failure, fall back to a single evidence goal covering the whole question
- [ ] 2.4 Unit-test the planner directly against a handful of `evals/golden.jsonl` items, comparing produced plans to each item's own `expected_evidence`

## 3. Retriever node

- [ ] 3.1 Implement dispatch logic mapping plan evidence goals to `typed-retrieval-tools` calls (`retrieve_by_year`, `retrieve_by_report`, `retrieve_with_section_filter`), joining metric/entity text into the query string per call
- [ ] 3.2 Implement the per-iteration dispatch ceiling, prioritizing one call per planned year over exhaustive year×metric pairing when the plan would exceed it
- [ ] 3.3 Accumulate retrieved hits into state, keyed by the evidence goal they satisfy, without duplicating identical chunk ids already accumulated in a prior iteration

## 4. Critic node

- [ ] 4.1 Implement coverage checking: for each planned year (and report id where applicable), does accumulated evidence include at least one matching hit
- [ ] 4.2 Implement the bounded-retry decision: request a focused retrieval pass for missing slots only, incrementing iteration count, up to `max_iterations`
- [ ] 4.3 Implement the iteration-cap exit: once `max_iterations` is reached, proceed to synthesis and record remaining gaps in state rather than looping further

## 5. Synthesizer node

- [ ] 5.1 Assemble the final-answer prompt from all accumulated evidence across evidence goals, reusing/adapting `rag.py::_format_context()` for context formatting
- [ ] 5.2 Instruct the model to explicitly state "no evidence found" for any plan goal recorded as an uncovered gap, rather than omitting it or inventing a value
- [ ] 5.3 Implement citation-tag detection (reusing `ask()`'s `"chunk_id=" in answer.lower()` check) and the one-shot repair re-prompt when citations are missing but evidence was supplied
- [ ] 5.4 Assemble the final result dict matching `ask()`'s shape (`question`, `status`, `answer`, `citations`, `hits`) plus new `plan` and `iterations` fields

## 6. Graph wiring and entrypoint

- [ ] 6.1 Wire planner → retriever → critic → (loop or synthesizer) as a LangGraph state machine
- [ ] 6.2 Add a new CLI entrypoint (e.g. `hfx-agent-ask`) in `cli.py` and register it in `pyproject.toml`'s `[project.scripts]`, mirroring `ask_main`'s argument shape where reasonable
- [ ] 6.3 Smoke-test the full graph against `gq-002` (single_doc, low-risk) before running multi-hop items

## 7. Golden-set validation and baseline

- [ ] 7.1 Run `gq-001` (flagship) through the new agent; confirm evidence coverage across all requested years (2020–2023) compared against `phase1_baseline.md`'s "missed 2023 entirely" result
- [ ] 7.2 Run the remaining `multi_hop`/`yoy_metric`-tagged items (`gq-004`, `gq-007`, `gq-010`, `gq-012`, `gq-014`, `gq-017`, `gq-022`, `gq-024`, `gq-025`) and the `year_collision`-tagged items (`gq-019`, `gq-020`) through the agent
- [ ] 7.3 Re-run `gq-003` specifically to confirm the citation-repair path resolves the `answer_uncited` outcome recorded in `phase1_baseline.md`
- [ ] 7.4 Write `evals/phase2_baseline.md` with per-item outcomes, directly comparable to `evals/phase1_baseline.md`'s table format

## 8. Wrap-up

- [ ] 8.1 Confirm no changes were made to `corpus/parsed/`, `corpus/chunks/`, `data/chroma/`, `rag.py`, or the existing `hfx-ask` CLI (this change is additive only)
- [ ] 8.2 Add a Phase 2 follow-on note to `docs/phase-1.md` and update `PLAN.md`'s phase table to reflect Phase 2 as shipped
