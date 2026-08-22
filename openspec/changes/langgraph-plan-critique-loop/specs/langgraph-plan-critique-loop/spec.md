## ADDED Requirements

### Requirement: Question decomposition into evidence goals
The system SHALL decompose an incoming question into a structured plan of evidence goals (years, report ids, metrics, entities) before performing any retrieval, without retrieving evidence during this step.

#### Scenario: Multi-year question decomposed before retrieval
- **WHEN** a question spans multiple years and metrics (e.g. "How did container throughput and operating income move from 2020–2023?")
- **THEN** the system produces a plan identifying each target year and metric prior to issuing any retrieval calls

#### Scenario: Malformed planner output degrades safely
- **WHEN** the planning step's model output cannot be parsed as a valid plan after one retry
- **THEN** the system falls back to a single evidence goal covering the whole question rather than failing the request

### Requirement: Deterministic dispatch of typed retrieval calls from a plan
The system SHALL dispatch retrieval for a plan using deterministic, code-driven calls into the typed retrieval functions (year-scoped, report-scoped, section-filtered) rather than delegating tool invocation to the language model, and SHALL bound the total number of retrieval calls issued per planning iteration.

#### Scenario: Full year coverage for a multi-year plan
- **WHEN** a plan includes multiple target years
- **THEN** the system issues at least one retrieval call per planned year (up to the dispatch ceiling) and accumulates the results into the request's evidence state

#### Scenario: Dispatch ceiling prevents unbounded retrieval
- **WHEN** a plan's year/metric combinations would exceed the configured per-iteration dispatch ceiling
- **THEN** the system prioritizes at least one retrieval call per planned year over exhaustively covering every year/metric pair, and does not exceed the ceiling

### Requirement: Bounded sufficiency critique
The system SHALL check accumulated evidence against the plan's evidence goals after each retrieval pass, and SHALL either request additional retrieval for specifically missing goals or proceed to synthesis, up to a configured maximum number of iterations after which synthesis proceeds regardless of remaining gaps.

#### Scenario: Missing year triggers a bounded retry
- **WHEN** accumulated evidence has no hit for one of the plan's target years after a retrieval pass, and the iteration count is below the configured maximum
- **THEN** the system issues an additional retrieval pass focused on the missing year(s) rather than re-running the full plan from scratch

#### Scenario: Iteration cap forces synthesis with recorded gaps
- **WHEN** the configured maximum number of iterations is reached and evidence gaps remain
- **THEN** the system proceeds to synthesis and records which plan goals remain uncovered rather than looping further

### Requirement: Partial-coverage cited synthesis
The system SHALL synthesize a final answer from all accumulated evidence across evidence goals, citing chunk and page/section identifiers for every factual claim, and SHALL explicitly state the absence of evidence for any plan goal that remains uncovered rather than omitting it silently or inventing a value for it.

#### Scenario: Answer covers available years and flags missing ones
- **WHEN** synthesis runs with evidence covering some but not all of the plan's target years
- **THEN** the returned answer includes cited claims for the covered years and an explicit statement that no evidence was found for each uncovered year

### Requirement: Citation-format repair
When the synthesized answer omits required citation tags despite evidence having been supplied, the system SHALL attempt one repair pass (re-prompting with the same evidence and an explicit citation-format instruction) before marking the response as uncited.

#### Scenario: Missing citation triggers a repair attempt
- **WHEN** a synthesized answer contains no citation tags but evidence was available to the synthesis step
- **THEN** the system re-prompts once with a citation-format reminder before falling back to an uncited-response status if the repair attempt also lacks citations

### Requirement: Phase 2 golden-set comparison baseline
The project SHALL run the golden set's `multi_hop`, `yoy_metric`, and `year_collision`-tagged items through this system and record per-item outcomes in a baseline note directly comparable to the existing Phase 1 baseline.

#### Scenario: Baseline note recorded
- **WHEN** this capability is considered complete
- **THEN** `evals/phase2_baseline.md` exists summarizing per-item outcomes for the `multi_hop`/`yoy_metric`/`year_collision`-tagged golden items, in a format comparable to `evals/phase1_baseline.md`
