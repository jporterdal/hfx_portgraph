## ADDED Requirements

### Requirement: Hierarchical parent chunks
The system SHALL create parent chunks corresponding to document sections (prefer H2/H3 or equivalent heading structure from parse output), each with a stable `chunk_id`, `report_id`, and provenance.

#### Scenario: Section parents emitted
- **WHEN** a parsed document is chunked
- **THEN** parent records exist for major sections with identifiers usable as citation targets

### Requirement: Child passage chunks
The system SHALL create child chunks of approximately 300–800 tokens (or equivalent character budget if tokenizer unavailable) linked to a parent via `parent_id`, and SHALL store page range or section provenance on each child.

#### Scenario: Children link to parents
- **WHEN** chunking completes for a report
- **THEN** every child record includes `parent_id` referencing an existing parent and includes provenance fields for citation

### Requirement: Chunk artifacts are durable and rebuildable
Chunk records SHALL be written to a durable local artifact (e.g. JSONL per report) that can be deleted and regenerated from parse outputs without re-downloading PDFs.

#### Scenario: Rebuild chunks from parse
- **WHEN** chunk artifacts are deleted and the chunker is re-run
- **THEN** new chunk files are produced from existing parse outputs
