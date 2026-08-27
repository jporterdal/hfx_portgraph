## MODIFIED Requirements

### Requirement: Preserve citation provenance
Parsed outputs SHALL retain page identifiers and section/heading identifiers sufficient to cite claims later (page numbers preferred; section headings REQUIRED when pages are unavailable). Heading identifiers SHALL reflect actual document structure: text classified as page furniture by the furniture-detection signal (see "Strip page furniture" below) SHALL NOT be exported as if it were a distinct section heading, even when the source PDF's layout model itself labels that text as a heading.

#### Scenario: Page or section anchors exist
- **WHEN** a parse completes successfully
- **THEN** the artifact metadata includes per-section or per-block provenance referencing page and/or heading

#### Scenario: Repeated running header is not exported as a section heading
- **WHEN** a line of text (e.g. a letterhead, running header, or footer) is classified as page furniture by the furniture-detection signal, regardless of what label the PDF layout model assigned it
- **THEN** that text SHALL NOT be exported as a markdown heading that downstream chunking would treat as a new section boundary

## ADDED Requirements

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
