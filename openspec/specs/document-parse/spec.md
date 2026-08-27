## Purpose

Convert present-corpus PDFs into structured, provenance-preserving text (Markdown/tables) so downstream chunking, indexing, and citation can rely on stable, citable artifacts.

## Requirements

### Requirement: Parse present corpus PDFs to structured text
The system SHALL convert each `status: present` PDF selected for Phase 1 ingest into Markdown (and structured tables where available) using an open-source local parser (Docling by default).

#### Scenario: Spike documents parse
- **WHEN** `2023_annual_en` and `2023_financials_en` are parsed
- **THEN** each produces parse artifacts under a stable path keyed by report id

### Requirement: Preserve citation provenance
Parsed outputs SHALL retain page identifiers and section/heading identifiers sufficient to cite claims later (page numbers preferred; section headings REQUIRED when pages are unavailable). Heading identifiers SHALL reflect actual document structure: text classified as page furniture by the furniture-detection signal (see "Strip page furniture" below) SHALL NOT be exported as if it were a distinct section heading, even when the source PDF's layout model itself labels that text as a heading.

#### Scenario: Page or section anchors exist
- **WHEN** a parse completes successfully
- **THEN** the artifact metadata includes per-section or per-block provenance referencing page and/or heading

#### Scenario: Repeated running header is not exported as a section heading
- **WHEN** a line of text (e.g. a letterhead, running header, or footer) is classified as page furniture by the furniture-detection signal, regardless of what label the PDF layout model assigned it
- **THEN** that text SHALL NOT be exported as a markdown heading that downstream chunking would treat as a new section boundary

### Requirement: Strip page furniture
Parsed Markdown output SHALL exclude text classified as page furniture by a fused detection signal combining: (a) bounding-box position consistency across a document's pages, (b) fuzzy/normalized text-repetition tolerant of OCR and extraction errors, and (c) the source PDF layout model's own header/footer classification where available. An item SHALL be classified as furniture when at least two of these three signals corroborate each other, with one fast-track exception: the layout model's header/footer classification combined with fuzzy text-repetition alone is sufficient without requiring position corroboration. An item supported by only one signal SHALL NOT be classified as furniture. Every classification decision (furniture or not) SHALL be recorded in an auditable per-report sidecar, so stripped text remains traceable to its source location even though it is excluded from `document.md`.

#### Scenario: Corroborated furniture is stripped
- **WHEN** an item's fuzzy-normalized text repeats across multiple pages of a document AND (the layout model classifies it as a header/footer OR it sits at a consistent bounding-box position across those occurrences)
- **THEN** that item's text SHALL be excluded from the parsed Markdown output

#### Scenario: Single-signal matches are not stripped
- **WHEN** an item matches only one of the three signals (e.g. text repeats but its position is inconsistent across occurrences, or its position matches a known furniture band but its text does not repeat, or the layout model flags it but it is a singleton with no repeating text or corroborating position)
- **THEN** that item's text SHALL remain in the parsed Markdown output, and the ambiguous classification SHALL be recorded in the audit sidecar

#### Scenario: Furniture decisions are auditable
- **WHEN** a parse completes
- **THEN** a per-report sidecar SHALL record, for every item considered, its text, position, source label, and the furniture classification decision made

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
