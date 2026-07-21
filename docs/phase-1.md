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

## Parse quality gate

Before bulk indexing, confirm ≥3 golden items tagged `table_heavy` are answerable from spike parse Markdown/tables alone (no RAG). Record the outcome under `evals/phase1_parse_gate.md`.
