## MODIFIED Requirements

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
