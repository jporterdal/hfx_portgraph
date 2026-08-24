## MODIFIED Requirements

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
