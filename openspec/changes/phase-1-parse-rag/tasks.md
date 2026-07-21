## 1. Setup and dependencies

- [ ] 1.1 Add Phase 1 deps to `pyproject.toml` (Docling, chromadb or equivalent, ollama client) and gitignore parse/chunk/vector artifacts
- [ ] 1.2 Document Ollama prerequisites (embed model `nomic-embed-text` or `bge-m3`, chat model) in a short `docs/phase-1.md` or README section
- [ ] 1.3 Create output layout stubs: `corpus/parsed/`, `corpus/chunks/`, vector index path

## 2. Document parse (spike → gate → batch)

- [ ] 2.1 Implement `scripts/parse_corpus.py` (or package module) to parse a report id from `corpus/raw/` via Docling into `corpus/parsed/{report_id}/` with Markdown + table artifacts and provenance metadata
- [ ] 2.2 Spike-parse `2023_annual_en` and `2023_financials_en`; inspect table/heading quality
- [ ] 2.3 Run parse quality gate: confirm ≥3 `table_heavy` golden items are answerable from spike parse outputs alone; if not, trial Marker on financials and record the decision
- [ ] 2.4 Batch-parse all manifest `annual`/`financials` with `status: present`

## 3. Parent-child chunking

- [ ] 3.1 Implement chunker: H2/H3 (or equivalent) parents + 300–800 token children with `parent_id`, `report_id`, page/section provenance
- [ ] 3.2 Write `corpus/chunks/{report_id}.jsonl` (or equivalent) for each parsed report
- [ ] 3.3 Verify rebuild: delete one report’s chunk file and regenerate from parse artifacts

## 4. Naive RAG (embed → ask → cite)

- [ ] 4.1 Implement embed/index script: Ollama embeddings over child chunks into local Chroma (or chosen store); gitignore the index
- [ ] 4.2 Implement ask CLI: retrieve children → expand parents → generate answer with chunk/page (or section) citations
- [ ] 4.3 Implement insufficient-evidence path (empty retrieval / ungroundable → explicit “I don’t know”)
- [ ] 4.4 Smoke-ask one `single_doc` golden item and confirm citations appear

## 5. Baseline and Phase 1 exit

- [ ] 5.1 Run ask path on a golden subset including `gq-001` and record qualitative baseline notes under `evals/` (e.g. `evals/phase1_baseline.md`)
- [ ] 5.2 Update docs with parse → chunk → index → ask command sequence
- [ ] 5.3 Confirm Phase 1 exit: spike gate passed, v1 annual/financials indexed, citations + insufficiency paths demonstrated
