## ADDED Requirements

### Requirement: Local embeddings for child chunks
The system SHALL embed child chunks using a local Ollama embedding model and store vectors in a local vector index (not Neo4j).

#### Scenario: Index build
- **WHEN** embedding/indexing runs over chunked v1 reports
- **THEN** child chunks are queryable by similarity search from a local index

### Requirement: Cited naive RAG answers
The system SHALL provide an ask interface that retrieves relevant child chunks, expands parent context, and returns an answer that cites chunk and page (or section) identifiers for claims.

#### Scenario: Answer with citations
- **WHEN** a user asks a question answerable from indexed chunks
- **THEN** the response includes one or more citations referencing chunk ids and page or section provenance

### Requirement: Explicit insufficiency
When retrieval returns no useful evidence or the model cannot ground claims in retrieved chunks, the system MUST return an explicit insufficient-evidence / “I don’t know” style result rather than uncited factual claims.

#### Scenario: No evidence path
- **WHEN** a question has no supporting retrieved chunks
- **THEN** the system indicates insufficiency and does not invent financial figures

### Requirement: Golden baseline smoke
The project SHALL run the ask path against a subset of `evals/golden.jsonl` (including at least the flagship `gq-001` and one `single_doc` item) and record qualitative baseline notes for Phase 2 comparison.

#### Scenario: Baseline notes recorded
- **WHEN** Phase 1 naive RAG is considered complete
- **THEN** a short baseline note exists (e.g. in `evals/` or project docs) summarizing smoke results on the chosen golden subset
