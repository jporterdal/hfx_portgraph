## Why

Phase 0 delivered a local Port of Halifax PDF corpus and a golden eval set, but nothing yet turns those PDFs into retrievable, citable text. PLAN.md Phase 1 is the next learning milestone: OSS parse, parent-child chunking, and Ollama naive RAG with citations—before LangGraph or Neo4j add agent/graph complexity.

## What Changes

- Parse inventoried PDFs with an open-source pipeline (Docling preferred) into Markdown + structured tables with page/section provenance
- Build hierarchical parent-child chunks (section parents, passage children) stored locally
- Embed child chunks with a local Ollama embedding model and index them in a lightweight vector store (not Neo4j yet)
- Provide a naive RAG ask path: retrieve children → expand parents → answer with chunk/page citations
- Fail closed on insufficient evidence (explicit “I don’t know” / no citation → no claim)
- Record a baseline golden-set run (qualitative or simple coverage log)—not a full LLM-as-judge harness
- No LangGraph agent loops and no Neo4j in this change

## Capabilities

### New Capabilities
- `document-parse`: Convert corpus PDFs to Markdown/tables while preserving page and section identifiers for citations
- `parent-child-chunking`: Split parsed documents into hierarchical parent sections and child passages with stable IDs and provenance
- `naive-rag`: Local embeddings + similarity retrieval + cited answers over parent-child chunks (vector store only)

### Modified Capabilities

(none — Phase 0 `report-corpus` and `golden-eval-set` remain as-is; this change consumes them)

## Impact

- New dirs likely under `data/` or `corpus/parsed/` and `corpus/chunks/` (gitignored binaries/artifacts as appropriate)
- New Python deps: Docling (or Marker), Ollama client, vector store (Chroma or equivalent)
- Runtime dependency: local Ollama with an embedding model (e.g. `nomic-embed-text`) and a small chat model for answers
- Scripts/CLI for parse → chunk → index → ask
- Uses Phase 0 `corpus/manifest.yaml` `present` PDFs and `evals/golden.jsonl` for baseline smoke
- Unblocks Phase 2 LangGraph loops over the same retrieval substrate
- **Known gap (documented in design):** annual-report infographic KPIs may be missing from Docling Markdown; follow-on path is design-heavy detection → local Ollama VLM on figure crops (Marker useful as crop source), not Marker-as-primary parser
