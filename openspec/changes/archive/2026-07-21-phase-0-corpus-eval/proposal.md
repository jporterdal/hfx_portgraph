## Why

Later RAG and graph phases need a stable Port of Halifax report corpus and a typed golden Q&A set before any parsing, embeddings, or agents are built. Without inventory hygiene and eval-first questions, Phase 1+ will optimize against the wrong failure modes (tables, YoY metrics, bilingual docs, year collisions).

## What Changes

- Add a local corpus layout under `corpus/` for Port of Halifax public reports PDFs
- Add a machine-readable manifest listing year, report type, language, source URL, and file path
- Acquire PDFs via a curated URL catalog, Wayback-assisted automated fetch, and manual browser fallback (not live HTML scrape or Cloudflare bypass)
- Add a golden evaluation set (20–40 items) with expected evidence shape and query-type tags
- Document hard failure-mode cases (table-heavy, bilingual, year-label collision) as first-class eval items
- No LangGraph, Neo4j, embeddings, or PDF parsing pipelines in this change

## Capabilities

### New Capabilities
- `report-corpus`: Acquire, store, and inventory Port of Halifax public report PDFs with a durable manifest
- `golden-eval-set`: Maintain a tagged golden Q&A dataset with evidence hints for measuring later retrieval/agent quality

### Modified Capabilities

(none — greenfield project)

## Impact

- New directories: `corpus/`, `evals/`
- New artifacts: `corpus/manifest.yaml`, curated URL catalog, `evals/golden.jsonl`, `scripts/fetch_corpus.py` (catalog → live PDF URL attempt → Wayback → leave gaps for manual drop)
- Network dependencies: Port of Halifax PDF/`wp-content` URLs and Internet Archive Wayback Machine; live reports HTML is optional inventory reference only
- No Cloudflare bypass tooling (Playwright/FlareSolverr/etc.) in Phase 0
- No application runtime, vector DB, or graph DB yet
- Unblocks Phase 1a parse spike and Phase 1b naive RAG against a fixed eval baseline
