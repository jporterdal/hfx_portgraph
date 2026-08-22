## Purpose

Convert present-corpus PDFs into structured, provenance-preserving text (Markdown/tables) so downstream chunking, indexing, and citation can rely on stable, citable artifacts.

## Requirements

### Requirement: Parse present corpus PDFs to structured text
The system SHALL convert each `status: present` PDF selected for Phase 1 ingest into Markdown (and structured tables where available) using an open-source local parser (Docling by default).

#### Scenario: Spike documents parse
- **WHEN** `2023_annual_en` and `2023_financials_en` are parsed
- **THEN** each produces parse artifacts under a stable path keyed by report id

### Requirement: Preserve citation provenance
Parsed outputs SHALL retain page identifiers and section/heading identifiers sufficient to cite claims later (page numbers preferred; section headings REQUIRED when pages are unavailable). The full per-item provenance list SHALL be persisted as a durable sidecar artifact, not only a truncated sample, so downstream chunking can resolve page-level citations without re-parsing the source PDF.

#### Scenario: Page or section anchors exist
- **WHEN** a parse completes successfully
- **THEN** the artifact metadata includes per-section or per-block provenance referencing page and/or heading

#### Scenario: Full provenance persisted for downstream use
- **WHEN** a parse completes successfully
- **THEN** `corpus/parsed/{report_id}/provenance.json` exists and contains the complete per-item provenance list (not truncated), in document order, with each item's label, page(s), and text preview

#### Scenario: Metadata sample remains scannable
- **WHEN** a parse completes successfully
- **THEN** `meta.json` continues to include `provenance_item_count` and a small human-scannable provenance sample, without inlining the full per-item list

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
</content>
