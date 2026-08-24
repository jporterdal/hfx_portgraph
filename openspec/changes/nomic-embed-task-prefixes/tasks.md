## 1. Implement prefixed embedding in rag.py

- [ ] 1.1 Add `prefix: str = ""` parameter to `_embed()`, prepended only to the string passed to `ollama.embed(input=...)` and to `ollama.embeddings(prompt=...)` in the fallback branch — the `texts`/`docs` list itself stays unmodified.
- [ ] 1.2 Add `_embed_documents(texts: list[str])` and `_embed_query(text: str)` wrappers that call `_embed()` with the correct prefix when `EMBED_MODEL.startswith("nomic-embed")`, and no prefix otherwise.
- [ ] 1.3 Update `index_reports()` to call `_embed_documents(docs)` instead of `_embed(docs)`.
- [ ] 1.4 Update `retrieve()` to call `_embed_query(question)` instead of `_embed([question])[0]`.
- [ ] 1.5 Add a short comment at the gate noting the future model→prefix-scheme registry idea (design.md Decision 4), so the next person adding a model sees why the check is a hardcoded `startswith` and where the idea to replace it lives.

## 2. Rebuild the vector index

- [ ] 2.1 Confirm Ollama is running with `nomic-embed-text` pulled (per `docs/phase-1.md`).
- [ ] 2.2 Run a full reindex with reset (`index_v1(reset=True)` via `cli.py`'s `--reset` flag) so no unprefixed vectors remain mixed with prefixed ones in the Chroma collection.
- [ ] 2.3 Spot-check that `retrieve()` returns results post-rebuild (e.g. via `scripts/scratch/inspect_rag_prompt.py` or a direct `ask()` call) before treating the rebuild as complete.

## 3. Refresh the golden baseline

- [ ] 3.1 Re-run the golden smoke subset used for the existing `naive-rag` baseline requirement (at minimum `gq-001` and one `single_doc` item) against the rebuilt index.
- [ ] 3.2 Update `evals/phase1_baseline.md` with the new results/notes, and call out that the embedding scheme changed (task-prefixed nomic embeddings) as the reason the numbers moved, if they did.

## 4. Verify the model gate

- [ ] 4.1 Confirm that setting `HFX_EMBED_MODEL=bge-m3` (or any non-`nomic-embed` value) results in unprefixed embedding calls — no `search_document:`/`search_query:` text sent to Ollama.
