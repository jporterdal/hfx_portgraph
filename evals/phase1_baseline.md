# Phase 1 naive RAG baseline

**Status:** blocked on local Ollama (not installed in the apply environment as of 2026-07-21).

## Completed before RAG smoke

- Docling parse spike + gate: `evals/phase1_parse_gate.md` (**PASS**)
- Batch parse: all 8 v1 `annual`/`financials` `present` reports under `corpus/parsed/`
- Parent-child chunks: `corpus/chunks/*.jsonl` (~2223 records); rebuild verified

## Pending (run on a machine with Ollama)

```bash
ollama pull nomic-embed-text
ollama pull llama3.1
python scripts/index_corpus.py --v1-batch --reset
python scripts/ask.py --golden gq-003
python scripts/ask.py --golden gq-001
python scripts/ask.py "What is the capital of France?"   # expect insufficient_evidence
```

Record qualitative notes here after those runs (citation quality, multi-hop gaps, insufficiency behavior).
