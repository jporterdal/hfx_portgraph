## ADDED Requirements

### Requirement: Parse present corpus PDFs to structured text
The system SHALL convert each `status: present` PDF selected for Phase 1 ingest into Markdown (and structured tables where available) using an open-source local parser (Docling by default).

#### Scenario: Spike documents parse
- **WHEN** `2023_annual_en` and `2023_financials_en` are parsed
- **THEN** each produces parse artifacts under a stable path keyed by report id

### Requirement: Preserve citation provenance
Parsed outputs SHALL retain page identifiers and section/heading identifiers sufficient to cite claims later (page numbers preferred; section headings REQUIRED when pages are unavailable).

#### Scenario: Page or section anchors exist
- **WHEN** a parse completes successfully
- **THEN** the artifact metadata includes per-section or per-block provenance referencing page and/or heading

### Requirement: Parse quality gate before bulk index
The project SHALL NOT treat bulk indexing as complete until a human can answer at least three golden items tagged `table_heavy` using only the spike parse outputs (no embeddings required).

#### Scenario: Table-heavy gate
- **WHEN** the parse spike is reviewed
- **THEN** at least three `table_heavy` golden questions are answerable from the parsed Markdown/tables alone, or the parser choice is revised and the gate re-run

### Requirement: Batch parse v1 annual and financials
After the spike gate passes, the system SHALL support parsing all manifest reports with `report_type` in `{annual, financials}` and `status: present`.

#### Scenario: V1 set parsed
- **WHEN** Phase 1 parse batch completes
- **THEN** each such present report has corresponding parse artifacts
