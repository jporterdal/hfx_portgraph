## Purpose

Maintain a tagged golden Q&A dataset with evidence hints for measuring later retrieval and agent quality over the Port of Halifax report corpus.

## Requirements

### Requirement: Golden eval set file exists
The system SHALL maintain `evals/golden.jsonl` containing one JSON object per line, each representing a single evaluation question against the Port of Halifax report corpus.

#### Scenario: File is loadable
- **WHEN** Phase 0 eval authoring is complete
- **THEN** `evals/golden.jsonl` exists and each non-empty line parses as a JSON object

### Requirement: Golden item schema
Each golden item SHALL include:
- `id` (stable unique string)
- `question` (natural language)
- `tags` (array of strings)
- `expected_evidence` (object including at least a `years` array)
- `notes` (string describing what correct grounding looks like)

#### Scenario: Minimal valid item
- **WHEN** a golden item is added
- **THEN** it has `id`, `question`, `tags`, `expected_evidence.years`, and `notes`

### Requirement: Query-type tags
Golden items SHALL use tags drawn from this controlled set: `single_doc`, `yoy_metric`, `narrative`, `multi_hop`, `table_heavy`, `bilingual`, `year_collision`. Additional tags MUST NOT be required for Phase 0 validity. Items MUST NOT introduce uncontrolled tag vocabulary in the committed golden set.

#### Scenario: Tagged multi-year metric question
- **WHEN** a question asks how a metric moved across years
- **THEN** its `tags` include `yoy_metric` (and typically `multi_hop` or `table_heavy` when applicable)

### Requirement: Coverage size and tagging rate
The golden set SHALL contain between 20 and 40 items inclusive, and at least 80% of items SHALL have one or more tags from the controlled set.

#### Scenario: Phase 0 size gate
- **WHEN** Phase 0 eval work is marked complete
- **THEN** item count is in [20, 40] and tagged fraction is ≥ 0.8

### Requirement: Hard failure-mode coverage
The golden set SHALL include at least three deliberately hard items that collectively cover table-heavy evidence, year-label collision risk, and bilingual difficulty when bilingual PDFs exist in the corpus; if bilingual PDFs are absent, the set SHALL document that gap in `evals/README.md` and still cover table-heavy and year-collision cases.

#### Scenario: Hard cases present
- **WHEN** Phase 0 eval work is marked complete
- **THEN** at least one item is tagged `table_heavy`, at least one is tagged `year_collision`, and either at least one is tagged `bilingual` or `evals/README.md` states bilingual corpus gap

### Requirement: Evidence hints link to corpus
`expected_evidence` MUST reference corpus identity via `report_ids` and/or filenames consistent with `corpus/manifest.yaml`, and MUST allow optional `metrics`, `entities`, and `page_hint` fields to guide later grading.

#### Scenario: Flagship temporal question
- **WHEN** the flagship question about container throughput and operating income from 2020–2023 with strategic initiative drivers is included
- **THEN** it has tags reflecting multi-year / multi-hop intent and `expected_evidence.years` including 2020–2023
