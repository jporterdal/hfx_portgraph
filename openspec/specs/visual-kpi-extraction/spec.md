## Purpose

Recover chart-/icon-borne KPIs (Sources of Revenue splits, cargo-stats bars, at-a-glance dashboards)
that Docling's text parse loses to `<!-- image -->` placeholders, by detecting design-heavy pages,
sourcing a figure crop for each, and extracting structured, citable facts via a local Ollama vision
model.

## Requirements

### Requirement: Detect design-heavy pages from existing parse artifacts
The system SHALL scan already-parsed Docling output under `corpus/parsed/{report_id}/` and flag
pages as design-heavy when they exhibit a high figure-to-text ratio, dense `<!-- image -->` stubs,
or dashboard-style section headings (e.g. "at-a-glance", "sources of revenue", cargo stats) with
numeric labels but no adjacent values in the Markdown.

#### Scenario: Known infographic pages are flagged
- **WHEN** the detector runs against `corpus/parsed/2023_annual_en/`
- **THEN** the Sources of Revenue page and at least one cargo-stats page are flagged as design-heavy

#### Scenario: Ordinary narrative pages are not flagged
- **WHEN** the detector runs against `corpus/parsed/2023_annual_en/`
- **THEN** prose-only sections with real tables (e.g. financial statement pages) are not flagged

### Requirement: Source a figure crop for each flagged page
For each design-heavy page, the system SHALL obtain an image crop suitable for VLM input, preferring
Docling's own exported image bytes and falling back to Marker JPEG crops or a full-page render when
Docling has no image for that figure.

#### Scenario: Docling image available
- **WHEN** a flagged page has a Docling-exported image for its figure
- **THEN** that image is used as the crop source without invoking Marker

#### Scenario: Docling has only a placeholder
- **WHEN** a flagged page's figure has no Docling-exported image (only a `<!-- image -->` stub)
- **THEN** the system falls back to a Marker crop or full-page render for that figure

### Requirement: Extract structured KPI facts via local Ollama VLM
The system SHALL run a local, vision-capable Ollama model against each sourced crop and produce
structured facts with `label`, `value`, `unit`, `year`, `report_id`, `page`, and `figure_id` fields.

#### Scenario: Sources of Revenue extraction
- **WHEN** the VLM runs against the `2023_annual_en` Sources of Revenue crop
- **THEN** the output includes labeled percentage facts consistent with values already confirmed via
  the Marker crop spike (e.g. Cargo and Real Estate splits), each carrying page and figure
  provenance

#### Scenario: Cargo-stats extraction
- **WHEN** the VLM runs against one `2023_annual_en` cargo-stats crop
- **THEN** the output includes at least one labeled numeric fact with page and figure provenance

### Requirement: Persist extracted facts to a citable sidecar
Extracted facts SHALL be written to `corpus/kpi_facts/{report_id}.jsonl`, mirroring the
`corpus/chunks/` layout convention, without being written into `data/chroma/` or any Neo4j store
until an explicit integration decision is recorded.

#### Scenario: Sidecar written, index untouched
- **WHEN** extraction completes for `2023_annual_en`
- **THEN** `corpus/kpi_facts/2023_annual_en.jsonl` exists with the extracted facts
- **AND** `data/chroma/` is unchanged by the extraction run

### Requirement: Record the RAG/graph integration decision
The project SHALL explicitly record, in this change's design or proposal, whether `kpi_facts`
join the Phase 1 vector index, wait for Phase 3 Neo4j Metric nodes, both, or neither, before this
change is considered complete.

#### Scenario: Decision recorded
- **WHEN** the spike's extraction results are reviewed
- **THEN** the design or proposal document states the chosen integration path and rationale
</content>
