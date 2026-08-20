# Phase 1 — Parse, parent-child chunks, naive RAG

Builds on Phase 0 corpus + golden eval. Local stack only.

## Prerequisites

1. Phase 0 PDFs present (`python scripts/validate_phase0.py` should PASS).
2. [Ollama](https://ollama.com/) installed and running.
3. Pull models:

```bash
ollama pull nomic-embed-text   # embeddings (or: ollama pull bge-m3)
ollama pull llama3.1           # chat answers (8b/latest tag is fine for Phase 1)
```

Optional env overrides:

| Variable | Default | Purpose |
|---|---|---|
| `HFX_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `HFX_CHAT_MODEL` | `llama3.1` | Ollama chat model |
| `HFX_CHROMA_DIR` | `data/chroma` | Vector index path |

## Layout

| Path | Contents |
|---|---|
| `corpus/parsed/{report_id}/` | `document.md`, `meta.json`, optional tables |
| `corpus/chunks/{report_id}.jsonl` | parent + child chunk records |
| `data/chroma/` | Chroma persistent index (gitignored) |

## Pipeline

```bash
source .venv/bin/activate
pip install -e .

# 1) Parse (spike first)
python scripts/parse_corpus.py --report-id 2023_annual_en
python scripts/parse_corpus.py --report-id 2023_financials_en

# After table-heavy gate: batch annual + financials
python scripts/parse_corpus.py --v1-batch

# 2) Chunk
python scripts/chunk_corpus.py --report-id 2023_annual_en
python scripts/chunk_corpus.py --v1-batch

# 3) Embed / index
python scripts/index_corpus.py --v1-batch

# 4) Ask
python scripts/ask.py "What was operating income for 2023?"
python scripts/ask.py --golden gq-003
```

### What each step does

1. **Parse** — `parse.py` runs Docling's `DocumentConverter` over the raw PDF, exports the
   document to Markdown, and walks Docling's item iterator to capture best-effort page-number
   provenance per text item. The full per-item provenance list is persisted as a
   `provenance.json` sidecar (not just a truncated sample in `meta.json`), so chunking can
   resolve page-level citations without re-parsing the PDF. Markdown tables are regex-extracted
   into a `tables.md` sidecar for manual QA. Idempotent by default (skips if `document.md` +
   `meta.json` + `provenance.json` all already exist); pass `--force` to redo.

2. **Chunk** — `chunk.py` splits each report's Markdown on H2/H3 headings to build **parent**
   chunks (full section text) and packs each section's paragraphs into **child** chunks (~500
   tokens, 300–800 range, using a ~4-chars/token heuristic since no real tokenizer is wired up).
   Parent and child records are interleaved in one JSONL per report, linked by `parent_id`. Page
   provenance is resolved (not absent): parent `page_start`/`page_end` come from positionally
   matching each section heading against `provenance.json`'s `section_header` rows; child
   `page_start`/`page_end` come from positionally matching the child's paragraphs against the
   section's passage-level provenance rows, falling back to the parent's range
   (`page_source: "inherited"`) when that finer match doesn't resolve. A `page_source` field
   (`"matched"` / `"inherited"` / `None`) marks how each range was derived.

3. **Embed / index** — `rag.py` embeds only the child chunks via Ollama (`nomic-embed-text` by
   default) and upserts them into a local Chroma `PersistentClient` under `data/chroma/`, all in
   one collection (`hfx_child_chunks`) with metadata (`report_id`, `section`, `heading`, page
   fields).

4. **Ask** — embeds the question, retrieves the top-k child chunks from Chroma, then widens each
   hit back to its parent section text by re-reading the chunk JSONL — narrow retrieval, full-
   context answer. The chat prompt requires citations in `[chunk_id=...; page_start=...]` form; a
   lightweight check downgrades the result to `answer_uncited` if the model doesn't comply.

## Parse quality gate

Before bulk indexing, confirm ≥3 golden items tagged `table_heavy` are answerable from spike parse Markdown/tables alone (no RAG). Record the outcome under `evals/phase1_parse_gate.md`.
