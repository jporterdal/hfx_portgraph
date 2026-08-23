## 1. Design-heavy page detection

- [x] 1.1 Write a detector that reads `corpus/parsed/2023_annual_en/` artifacts and scores pages by figure:text ratio, `<!-- image -->` stub density, and dashboard-style heading match
- [x] 1.2 Run the detector against `2023_annual_en`; confirm it flags the Sources of Revenue page and at least one cargo-stats page
- [x] 1.3 Spot-check for false positives: confirm prose/real-table pages (e.g. financial statements) are not flagged

## 2. Figure-crop sourcing

- [x] 2.1 For each flagged page, attempt Docling image export first; record whether usable image bytes exist
- [x] 2.2 For pages where Docling only has a placeholder, generate a fallback crop via Marker (reuse the existing spike output where possible) or a full-page render (`pypdfium2`)
- [x] 2.3 Compare crop quality/precision across sources on at least one shared page; pick and document the default source order

## 3. Local Ollama VLM extraction

- [x] 3.1 Identify and pull a vision-capable local Ollama model; record the choice and why
- [x] 3.2 Run extraction against the Sources of Revenue crop; verify output values are consistent with the known 41%/35% split already confirmed via the Marker spike
- [x] 3.3 Run extraction against one cargo-stats crop; verify at least one labeled numeric fact comes out with page/figure provenance
- [x] 3.4 Write extracted facts to `corpus/kpi_facts/2023_annual_en.jsonl` (label, value, unit, year, report_id, page, figure_id)

## 4. Integration decision

- [x] 4.1 Review spike results; decide whether `kpi_facts` join the Phase 1 Chroma index, wait for Phase 3 Neo4j Metric nodes, both, or neither yet
- [x] 4.2 Record the decision and rationale in this change's design.md or proposal.md
- [x] 4.3 If the decision is "join Phase 1 index now," scope that as explicit follow-up tasks here (do not silently implement without updating this task list first)

## 5. Wrap-up

- [x] 5.1 Update `phase-1-parse-rag/tasks.md` Section 6 to note it has been superseded by this change (already done when Phase 1 was archived — see `openspec/changes/archive/2026-08-09-phase-1-parse-rag/tasks.md` Section 6)
- [x] 5.2 Document the spike outcome (pass/fail/partial) and command sequence in a short note under `evals/` or `docs/`
