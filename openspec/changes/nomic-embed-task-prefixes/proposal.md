## Why

`_embed()` in `rag.py` sends raw chunk text and raw questions straight to Ollama without nomic-embed-text's documented `search_document:`/`search_query:` task prefixes. Nomic's model card recommends these prefixes to separate document and query representations in embedding space; omitting them leaves retrieval quality on the table for no reason other than an oversight.

## What Changes

- `_embed()` (or a thin wrapper around it) applies `search_document: ` to child-chunk text during indexing and `search_query: ` to the question during retrieval — prefixing only the string sent to Ollama, never the text stored in Chroma or shown back to the LLM as context.
- The prefix is gated on `EMBED_MODEL` starting with `nomic-embed` (via a small conditional), since `bge-m3` (already documented as an alternative in `docs/phase-1.md`/`PLAN.md`) does not use this convention. Prefixing unconditionally would silently corrupt embeddings for anyone running with `HFX_EMBED_MODEL=bge-m3`.
- `design.md` documents, as a **future idea only** (not built now), a small local registry mapping embed-model name → prefix scheme, so adding the next model doesn't mean another `if` branch in `_embed()`.
- **Required follow-up, not optional cleanup:** the existing Chroma collection at `CHROMA_DIR` was built with unprefixed document vectors. Shipping prefixed query embeddings against that stale index would be worse than doing nothing (queries and documents drift further apart, not closer). `tasks.md` includes a mandatory `index_v1(reset=True)` rebuild and a mandatory update to `evals/phase1_baseline.md`, since that baseline was captured against the unprefixed index and becomes stale the moment this ships.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `naive-rag`: "Local embeddings for child chunks" requirement extended — embedding calls SHALL apply the model's documented task-prefix convention when one is known for the configured `EMBED_MODEL`, distinguishing document embedding from query embedding.

## Impact

- **Code:** `hfx_portgraph/rag.py` (`_embed`, `index_reports`, `retrieve`).
- **Data:** `data/chroma` (or `HFX_CHROMA_DIR`) — full reindex required; old and new vectors are not compatible in the same collection.
- **Docs:** `evals/phase1_baseline.md` — must be re-captured post-reindex; the existing notes reflect the unprefixed embedding scheme.
- **No API/CLI surface change** — `cli.py`'s existing `--reset` flag already covers the required rebuild.
