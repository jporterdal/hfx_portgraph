## Purpose

Provide a locally-embedded, citation-grounded question-answering path over indexed child chunks, with explicit handling of insufficient evidence and a baseline smoke test against the golden eval set.

## Requirements

### Requirement: Local embeddings for child chunks
The system SHALL embed child chunks using a local Ollama embedding model and store vectors in a local vector index (not Neo4j). When the configured embedding model has a documented task-prefix convention for distinguishing document embeddings from query embeddings (e.g. nomic-embed-text's `search_document:` / `search_query:`), the system SHALL apply the document-side prefix when embedding child chunks for indexing and the query-side prefix when embedding a question for retrieval, without altering the stored chunk text or the text surfaced to the LLM as context. When the configured model has no known prefix convention, text SHALL be embedded unprefixed.

#### Scenario: Index build
- **WHEN** embedding/indexing runs over chunked v1 reports
- **THEN** child chunks are queryable by similarity search from a local index

#### Scenario: Nomic document prefix applied on index
- **WHEN** the configured embedding model is `nomic-embed-text` and child chunks are embedded for indexing
- **THEN** the text sent to Ollama is prefixed with `search_document: `
- **AND** the chunk text stored in the vector index and returned as retrieval context remains unprefixed

#### Scenario: Nomic query prefix applied on retrieval
- **WHEN** the configured embedding model is `nomic-embed-text` and a question is embedded for retrieval
- **THEN** the text sent to Ollama is prefixed with `search_query: `

#### Scenario: Non-nomic model embedded unprefixed
- **WHEN** the configured embedding model does not match a known task-prefix convention (e.g. `bge-m3`)
- **THEN** child chunks and questions are embedded without any added prefix

### Requirement: Cited naive RAG answers
The system SHALL provide an ask interface that retrieves relevant child chunks, expands parent context, and returns an answer that cites chunk and page (or section) identifiers for claims.

#### Scenario: Answer with citations
- **WHEN** a user asks a question answerable from indexed chunks
- **THEN** the response includes one or more citations referencing chunk ids and page or section provenance

### Requirement: Explicit insufficiency
When retrieval returns no useful evidence or the model cannot ground claims in retrieved chunks, the system MUST return an explicit insufficient-evidence / "I don't know" style result rather than uncited factual claims.

#### Scenario: No evidence path
- **WHEN** a question has no supporting retrieved chunks
- **THEN** the system indicates insufficiency and does not invent financial figures

### Requirement: Golden baseline smoke
The project SHALL run the ask path against a subset of `evals/golden.jsonl` (including at least the flagship `gq-001` and one `single_doc` item) and record qualitative baseline notes for Phase 2 comparison.

#### Scenario: Baseline notes recorded
- **WHEN** Phase 1 naive RAG is considered complete
- **THEN** a short baseline note exists (e.g. in `evals/` or project docs) summarizing smoke results on the chosen golden subset
</content>
