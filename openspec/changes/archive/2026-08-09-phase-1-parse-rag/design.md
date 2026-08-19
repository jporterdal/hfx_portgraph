## Context

Phase 0 is archived and synced: local PDFs in `corpus/raw/` with `manifest.yaml`, plus `evals/golden.jsonl`. PLAN.md Phase 1 ships OSS parse + parent-child chunking + Ollama naive RAG with citations—explicitly before LangGraph (Phase 2) and Neo4j (Phase 3).

Constraints carried forward:
- Every claim must be citable to chunk/page
- Table fidelity is the highest parse risk for financials; **visual / infographic KPI loss** is the highest parse risk for annual reports
- Prefer throwaway local vector store over Neo4j for Phase 1
- Golden set is for baseline smoke, not automated scoring yet

Phase 1a handoff from Phase 0: prefer `2023_annual_en.pdf` and `2023_financials_en.pdf` for the parse spike.

**Spike follow-up (2026-07-21):** Docling passed the table-heavy gate, but `2023_annual_en` drops chart-/icon-borne figures (many `<!-- image -->` stubs). A limited Marker trial on annual pages 0–12 did **not** recover those numbers into Markdown; it did export figure JPEG crops useful for a later vision pass.

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

### 1. Parser: Docling default; Marker is not the annual-report fix
- **Choice:** Keep Docling as the default PDF → Markdown + tables path for Phase 1 ingest.
- **Why:** PLAN.md OSS swap for LlamaParse; financials spike gate passed on Docling; Marker-on-annuals did not recover chart-borne KPIs into text.
- **Marker role (revised):** Not the primary escape hatch for infographic pages. Marker remains optional for (a) a financials table re-trial if a future PDF fails Docling grids, and (b) **figure-crop generation** — Marker’s on-disk JPEGs are a convenient input for a VLM second stage when Docling only emits image placeholders.
- **Alternatives considered:** Marker-only replace; Docling∥Marker text merge; Unstructured; PyMuPDF custom.

### 1b. Follow-on path: design-heavy pages → local VLM on figures
*(Sketched for post–Phase 1 exit or a small follow-on change; not required to close Phase 1.)*

```
[Raw PDF]
    │
    ▼
[Docling] ──► Markdown + tables + provenance
    │
    │  detect design-heavy / infographic pages
    │  (heuristics: many picture/figure blocks, few
    │   paragraph tokens, dense <!-- image --> /
    │   empty chart sections, high figure:text ratio)
    │
    ├─ prose / real tables ──► keep Docling MD (chunk/index as today)
    │
    └─ design-heavy pages
            │
            ▼
       [Figure crops]
            │  prefer: Docling-exported images if available
            │  fallback / alternate: Marker figure JPEGs
            │  or full-page renders (pypdfium2 / similar)
            │
            ▼
       [Local VLM via Ollama]
            │  structured extract: label → value → unit → year
            │  + page / figure id for citation
            │
            ▼
       [kpi_facts.jsonl sidecar]  (optional MD appendix)
            │
            ▼
       later: embed/index facts or Phase 3 Metric nodes
```

- **Choice:** Treat visual KPI recovery as a **routed second stage**, not a second full-document text parser. Host the VLM on the existing local **Ollama** server (distinct from Marker/Surya’s `llama-server` OCR dependency).
- **Why:** Annual at-a-glance / cargo-stats / sources-of-revenue pages encode values in graphics; text-layer tools (Docling and Marker) leave percentages and chart series behind. Marker spike showed category labels without pie/bar values while the crop (`_page_4_Figure_9.jpeg`) still contained e.g. 41% Cargo / 35% Real Estate.
- **Detection (initial heuristics, to refine in a spike):**
  - High count of picture/figure blocks or `<!-- image -->` stubs per page
  - Low body-text density relative to figures
  - Section titles typical of dashboards (“at-a-glance”, “sources of revenue”, cargo stats) with missing numeric pairs beside labels
- **Citation:** Facts must retain `report_id`, page, and figure/crop id (or page render id) so answers can cite the visual source, not only a Markdown chunk.
- **Non-goal for this sketch:** Cloud one-shot LM parse APIs; replacing Docling corpus-wide with a VLM.

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

- **[Risk] Docling mishandles financial tables** → Mitigation: parse spike gate; optional Marker re-trial on financials; do not index until gate passes.
- **[Risk] Annual-report infographics lose KPIs in Markdown** → Mitigation: Phase 1 gate may still pass on loose text + real tables; document the gap; follow-on Docling → design-heavy detect → Ollama VLM on figure crops (Marker crops as alternate source); RAG insufficiency when only chart-borne evidence would answer.
- **[Risk] Weak or missing page numbers from parser** → Mitigation: require best-effort page metadata; fail citation quality checks in review; store section headings as fallback anchors.
- **[Risk] Ollama not installed / model not pulled** → Mitigation: document setup in README; scripts fail with clear errors. VLM follow-on needs a vision-capable Ollama model in addition to embed/chat.
- **[Risk] Marker full OCR path needs llama.cpp `llama-server`** → Mitigation: text-layer Marker (`--disable_ocr`) is enough for crop export; do not assume the Ollama daemon substitutes for Surya’s llama-server.
- **[Risk] Naive RAG fails multi-hop golden items** → Mitigation: expected for Phase 1; log baseline; Phase 2 agent loops address planning.
- **[Trade-off] Chroma vs Neo4j vectors** → Rebuild cost later when moving to Neo4j; acceptable for learning sequence.
- **[Trade-off] No automated answer scoring** → Manual/qualitative baseline only; keeps Phase 1 focused on pipeline mechanics.
- **[Trade-off] Defer VLM KPI path past Phase 1 exit** → Faster Phase 1 close; annual chart facts stay incomplete until the follow-on ships.

## Migration Plan

1. Add parse/chunk/index/ask scripts and deps to `pyproject.toml`
2. Spike-parse two PDFs → gate
3. Batch-parse + chunk + embed remaining annual/financials
4. Ask CLI smoke + golden subset baseline notes
5. Hand off retrieval substrate to Phase 2 (LangGraph wraps same tools)

Rollback: delete `corpus/parsed/`, `corpus/chunks/`, and vector index dirs; Phase 0 corpus untouched.

## Open Questions

- Exact Docling version/API surface once installed on this machine *(partially resolved: Docling in use; export-of-figure-bytes vs Marker crops still to confirm)*
- Whether bilingual FR PDFs enter the index if added to manifest later (default: same pipeline, not required for Phase 1 exit)
- Chat model size for answer generation given local hardware
- Which Ollama vision model to use for the VLM second stage (size vs accuracy on bar/pie crops)
- Whether design-heavy detection runs per-page at parse time or as a separate post-pass over parse artifacts
- Whether VLM outputs join the vector index in Phase 1-style RAG or wait for Phase 3 Metric nodes
- Whether to install llama.cpp `llama-server` later for Marker OCR/balanced mode, or keep Marker only as a crop helper with `--disable_ocr`
