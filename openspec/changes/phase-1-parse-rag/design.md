## Context

Phase 0 is archived and synced: local PDFs in `corpus/raw/` with `manifest.yaml`, plus `evals/golden.jsonl`. PLAN.md Phase 1 ships OSS parse + parent-child chunking + Ollama naive RAG with citations—explicitly before LangGraph (Phase 2) and Neo4j (Phase 3).

Constraints carried forward:
- Every claim must be citable to chunk/page
- Table fidelity is the highest parse risk
- Prefer throwaway local vector store over Neo4j for Phase 1
- Golden set is for baseline smoke, not automated scoring yet

Phase 1a handoff from Phase 0: prefer `2023_annual_en.pdf` and `2023_financials_en.pdf` for the parse spike.

## Goals / Non-Goals

**Goals:**
- Reliable PDF → Markdown/tables with page/section IDs for v1 catalog PDFs marked `present`
- Parent-child chunk graph on disk (or local DB) with `parent_id` + page refs
- Naive RAG CLI/notebook: embed → retrieve → answer with citations
- Parse-quality gate before full-corpus indexing (answer table-heavy questions from parse output alone)
- Baseline run notes against a subset of golden items

**Non-Goals:**
- LangGraph plan/critique loops (Phase 2)
- Neo4j, ontology extraction, or typed Cypher tools (Phase 3)
- Hybrid BM25+dense or Qdrant experiments (optional later)
- Full RAGAS / LLM-as-judge scoring harness
- Report compiler / multi-section research UX (Phase 4)
- LlamaParse or other cloud parse APIs

## Decisions

### 1. Parser: Docling first, Marker as escape hatch
- **Choice:** Default to Docling for PDF → Markdown + tables; try Marker on one hard financials PDF if Docling table quality fails the spike gate.
- **Why:** PLAN.md OSS swap for LlamaParse; Docling is the stated preference.
- **Alternatives:** Marker-only; Unstructured; PyMuPDF custom (more DIY).

### 2. Parse spike before bulk ingest
- **Choice:** Parse `2023_annual_en` + `2023_financials_en` first; manually verify ≥3 `table_heavy` golden questions are answerable from parse artifacts alone; only then batch remaining `present` annual/financials.
- **Why:** Bad tables poison embeddings and citations.
- **Alternatives:** Parse everything immediately (faster, higher rework risk).

### 3. Artifact layout
- **Choice:**
  - `corpus/parsed/{report_id}/` — markdown, tables sidecar, parse metadata (page map)
  - `corpus/chunks/{report_id}.jsonl` — parent + child records
  - Vector index under `.chroma/` or `data/chroma/` (gitignored)
- **Why:** Mirrors corpus IDs from Phase 0; easy to wipe and rebuild.
- **Alternatives:** Single SQLite blob; store chunks only in the vector DB (weaker citation debugging).

### 4. Chunking: H2/H3 parents, 300–800 token children
- **Choice:** Parent = heading section; child = 300–800 token passages with `parent_id`, `report_id`, `page_start`/`page_end` (or best-available page refs).
- **Why:** Matches PLAN.md Phase 1 learning outcome and citation needs.
- **Alternatives:** Fixed-size only; sentence windows; late chunking.

### 5. Embeddings + chat via Ollama
- **Choice:** `nomic-embed-text` (or `bge-m3` if already pulled) for embeddings; a small/local Llama 3.1 (or similar) for answer generation.
- **Why:** PLAN revised stack; keeps Phase 1 fully local.
- **Alternatives:** Cloud embeddings (out of scope for OSS learning path).

### 6. Vector store: Chroma (local)
- **Choice:** Embedded Chroma for child-chunk vectors; metadata filters by `report_id` / `year` when useful.
- **Why:** Minimal ops; Neo4j deferred; easy reset.
- **Alternatives:** Qdrant; FAISS; Neo4j vectors early (pulls Phase 3 forward).

### 7. Retrieval shape
- **Choice:** Similarity search over children → load parent section text for context → generate answer that must cite `chunk_id` + page when making claims; if retrieval empty or model cannot cite, return explicit insufficiency.
- **Why:** Teaches hierarchical retrieval without agent loops.
- **Alternatives:** Children-only context (weaker section coherence); parents-only (worse precision).

### 8. Scope of documents for v1 index
- **Choice:** Index `annual` + `financials` with `status: present` from manifest; `other` types optional / out of Phase 1 exit criteria.
- **Why:** Aligns with Phase 0 v1 coverage and golden evidence hints.

## Risks / Trade-offs

- **[Risk] Docling mishandles financial tables** → Mitigation: parse spike gate; Marker trial; do not index until gate passes.
- **[Risk] Weak or missing page numbers from parser** → Mitigation: require best-effort page metadata; fail citation quality checks in review; store section headings as fallback anchors.
- **[Risk] Ollama not installed / model not pulled** → Mitigation: document setup in README; scripts fail with clear errors.
- **[Risk] Naive RAG fails multi-hop golden items** → Mitigation: expected for Phase 1; log baseline; Phase 2 agent loops address planning.
- **[Trade-off] Chroma vs Neo4j vectors** → Rebuild cost later when moving to Neo4j; acceptable for learning sequence.
- **[Trade-off] No automated answer scoring** → Manual/qualitative baseline only; keeps Phase 1 focused on pipeline mechanics.

## Migration Plan

1. Add parse/chunk/index/ask scripts and deps to `pyproject.toml`
2. Spike-parse two PDFs → gate
3. Batch-parse + chunk + embed remaining annual/financials
4. Ask CLI smoke + golden subset baseline notes
5. Hand off retrieval substrate to Phase 2 (LangGraph wraps same tools)

Rollback: delete `corpus/parsed/`, `corpus/chunks/`, and vector index dirs; Phase 0 corpus untouched.

## Open Questions

- Exact Docling version/API surface once installed on this machine
- Whether bilingual FR PDFs enter the index if added to manifest later (default: same pipeline, not required for Phase 1 exit)
- Chat model size for answer generation given local hardware
