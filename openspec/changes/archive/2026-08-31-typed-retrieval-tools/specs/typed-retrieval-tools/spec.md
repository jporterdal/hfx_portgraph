## ADDED Requirements

### Requirement: Year-scoped multi-year retrieval
The system SHALL provide a retrieval function that accepts one or more target years and, for each requested year with matching indexed content, returns at least one hit for that year rather than relying on a single global similarity ranking across all years combined.

#### Scenario: Multi-year evidence coverage
- **WHEN** a caller requests retrieval scoped to a specific set of years (e.g. 2020–2023) for a metric that has passages indexed in each of those years
- **THEN** the returned hits include at least one hit per requested year that has matching indexed content, instead of a single year's passages crowding out the others

### Requirement: Report-scoped retrieval
The system SHALL provide a retrieval function that accepts one or more `report_id` values and restricts results to child chunks belonging to those reports, using existing Chroma metadata filtering (no re-indexing required).

#### Scenario: Single-report grounding
- **WHEN** a caller requests retrieval scoped to a specific `report_id`
- **THEN** every returned hit's metadata `report_id` matches one of the requested report ids

### Requirement: Report-type derivation without re-indexing
The system SHALL derive a report's type (annual vs. financials) from `corpus/manifest.yaml`'s `report_type` field for the requested `report_id`(s), and SHALL NOT require new Chroma metadata fields or re-indexing of existing chunk artifacts to support report-type-scoped retrieval.

#### Scenario: Report-type lookup for an unknown id
- **WHEN** a caller requests report-type-scoped retrieval for a `report_id` not present in `corpus/manifest.yaml`
- **THEN** the system raises a clear error identifying the unresolvable `report_id` rather than silently guessing a type or returning unfiltered results

### Requirement: Section-type-aware retrieval
The system SHALL provide a retrieval mode that classifies retrieved hits' section/heading text as primary-statement-like or note/footnote-like using a heuristic pattern match, and uses this classification to deprioritize note/footnote-labeled sections relative to primary-statement-labeled sections when both are returned for the same query.

#### Scenario: Statement vs. footnote collision
- **WHEN** a query's literal phrasing matches a note/footnote section (e.g. a numbered "Comparative figures" note) more strongly by raw similarity than the semantically correct primary statement section, and both are present in the retrieved candidate set
- **THEN** section-type-aware retrieval ranks the primary-statement-labeled section above the note/footnote-labeled section in the returned hits

### Requirement: Uniform hit shape across retrieval modes
Typed retrieval functions SHALL return hits in the same shape as the existing naive `retrieve()` function (`chunk_id`, `text`, `distance`, `metadata`, `parent_text`), so downstream consumers can use typed and naive hits interchangeably without a second data model.

#### Scenario: Drop-in context formatting
- **WHEN** hits returned by a typed retrieval function are passed to the existing `_format_context()` helper (or an equivalent context-assembly step)
- **THEN** the helper produces a citation-ready context block without requiring any typed-hit-specific handling

### Requirement: Golden-set evidence coverage validation
The project SHALL run the typed retrieval functions directly (without going through the LLM-backed `ask()` path) against every `multi_hop`, `yoy_metric`, and `year_collision`-tagged item in `evals/golden.jsonl`, and SHALL record per-item evidence-coverage results against each item's `expected_evidence` fields in a durable validation note.

#### Scenario: Coverage note recorded
- **WHEN** typed retrieval tools are considered complete for this change
- **THEN** a validation note (e.g. `evals/typed_retrieval_validation.md`) exists summarizing, per tagged golden item, whether the typed functions surfaced evidence covering the expected years/report ids and whether the `year_collision` items' section-type filtering avoided the known footnote-collision failure
