## Purpose

Produce durable, rebuildable parent/child chunk artifacts from parsed documents, preserving citation provenance so retrieval can return precise passages while allowing broader section context expansion.

## Requirements

### Requirement: Hierarchical parent chunks
The system SHALL create parent chunks corresponding to document sections (prefer H2/H3 or equivalent heading structure from parse output), each with a stable `chunk_id`, `report_id`, and provenance. Parent provenance SHALL include a resolved `page_start`/`page_end` range when the section's heading can be matched against parsed provenance, and SHALL indicate via a `page_source` field whether that range was directly matched or left unresolved.

#### Scenario: Section parents emitted
- **WHEN** a parsed document is chunked
- **THEN** parent records exist for major sections with identifiers usable as citation targets

#### Scenario: Parent page range resolved from provenance
- **WHEN** a section's heading is positionally matched against a `section_header` provenance row
- **THEN** the parent record's `page_start`/`page_end` reflect that row's page(s) and `page_source` is `"matched"`

#### Scenario: Parent page range left unresolved
- **WHEN** a section's heading cannot be matched against provenance (e.g. heading/anchor counts diverge before this section)
- **THEN** the parent record's `page_start`/`page_end` remain `None` and citation falls back to the section heading, consistent with existing insufficient-provenance handling

### Requirement: Child passage chunks
The system SHALL create child chunks of approximately 300–800 tokens (or equivalent character budget if tokenizer unavailable) linked to a parent via `parent_id`, and SHALL store a resolved page range on each child using the following precedence: (1) a direct match between the child's constituent paragraphs and parsed provenance rows, (2) inheritance of the parent section's resolved page range, (3) unresolved (`None`), in which case section provenance remains the citation fallback. Each child record SHALL carry a `page_source` field (`"matched"` or `"inherited"`) whenever a page range is populated.

#### Scenario: Children link to parents
- **WHEN** chunking completes for a report
- **THEN** every child record includes `parent_id` referencing an existing parent and includes provenance fields for citation

#### Scenario: Child page range directly matched
- **WHEN** a child's constituent paragraphs are positionally matched against non-heading provenance rows within its section
- **THEN** the child's `page_start`/`page_end` reflect the min/max pages of those rows and `page_source` is `"matched"`

#### Scenario: Child page range inherited from parent
- **WHEN** a child's paragraphs cannot be directly matched against provenance but its parent section has a resolved page range
- **THEN** the child's `page_start`/`page_end` are set to the parent's range and `page_source` is `"inherited"`

#### Scenario: Child page range unresolved
- **WHEN** neither the child nor its parent section can be matched against provenance
- **THEN** the child's `page_start`/`page_end` remain `None` and citation falls back to section heading, consistent with existing insufficient-provenance handling

### Requirement: Chunk artifacts are durable and rebuildable
Chunk records SHALL be written to a durable local artifact (e.g. JSONL per report) that can be deleted and regenerated from parse outputs without re-downloading PDFs.

#### Scenario: Rebuild chunks from parse
- **WHEN** chunk artifacts are deleted and the chunker is re-run
- **THEN** new chunk files are produced from existing parse outputs
</content>
