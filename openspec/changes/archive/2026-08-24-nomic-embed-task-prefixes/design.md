## Context

`_embed()` in `hfx_portgraph/rag.py` has exactly two callers:

- `index_reports()` → `_embed(docs)` — embeds child-chunk text for storage in Chroma.
- `retrieve()` → `_embed([question])` — embeds the user's question for similarity search.

This is a clean 1:1 split onto nomic-embed-text's `search_document:` / `search_query:` task-prefix convention — no chunk plays both roles. `_embed()` currently sends raw text to `ollama.embed()` (with a fallback to `ollama.embeddings()`), and neither prefixes anything.

`EMBED_MODEL` (`hfx_portgraph/paths.py:19`) defaults to `nomic-embed-text` but is overridable via `HFX_EMBED_MODEL`, and both `docs/phase-1.md` and `PLAN.md` name `bge-m3` as a documented alternative. `bge-m3` does not use nomic's prefix convention, so the prefixing logic cannot be unconditional.

Chroma persists to `CHROMA_DIR` (default `data/chroma`) across runs. Every vector already indexed there was embedded without a prefix. `evals/phase1_baseline.md` records eval notes captured against that unprefixed index.

## Goals / Non-Goals

**Goals:**
- Apply `search_document: ` / `search_query: ` prefixes at the point text is sent to Ollama, without altering the text stored in Chroma or shown to the LLM as context.
- Gate the prefix behind a check on `EMBED_MODEL` so switching to `bge-m3` (or anything else) doesn't silently mis-embed.
- Make the required reindex and baseline update explicit, ordered steps — not implied cleanup.

**Non-Goals:**
- Building a general model → prefix-scheme registry now. One model-conditional branch is enough for one model; a registry is speculative until there's a second prefix convention to support. Captured below as a future idea only.
- Changing `_embed()`'s per-text-loop call pattern to Ollama, batching, or its error handling — out of scope for this change.
- Making the prefix strings themselves configurable via env var — the prefix is fixed by the model's own documentation, not a project preference.

## Decisions

**1. Prefix at the Ollama call boundary, not on `docs`/`texts`.**
`index_reports()` passes `docs` both to `_embed()` and to `collection.upsert(documents=docs, ...)`, and `_format_context()` later renders stored `documents` back to the LLM as `CHILD:` text. Prefixing `docs` in place would leak `search_document: ` into stored chunks and into the LLM's evidence context. Instead, `_embed()` takes a `prefix: str = ""` argument and prepends it only to the string passed to `ollama.embed(input=...)` / `ollama.embeddings(prompt=...)`, per loop iteration. `index_reports()` and `retrieve()` pass the prefix in; the list handed to Chroma stays untouched.

**2. Named wrappers over a bare string parameter at call sites.**
Rather than callers writing `_embed(docs, "search_document: ")` (a literal easy to typo or swap between the two call sites), `_embed()` keeps the `prefix` parameter as its implementation, and two thin wrappers — `_embed_documents(texts)` and `_embed_query(text)` — hardcode the correct prefix and are what `index_reports()` and `retrieve()` actually call. This makes the document/query distinction visible at the call site instead of buried in a string literal.

**3. Model-conditional gate, not unconditional prefixing.**
Alternatives considered:
- *Always prefix* — simplest, but silently corrupts embeddings for anyone running `HFX_EMBED_MODEL=bge-m3`, which the project's own docs list as supported.
- *Model registry (name → prefix scheme)* — the "correct" long-term shape, but overbuilt for a codebase that currently names exactly two embed models in its docs and has one prefix convention to encode. Deferred (see below).
- *Model-conditional gate* (chosen) — `EMBED_MODEL.startswith("nomic-embed")` decides whether `_embed_documents`/`_embed_query` apply their prefix or pass text through unchanged. Cheap, correct for both currently-documented models, and centralizes the one branch point needed today.

**4. Future idea, not built now: local model→prefix-scheme registry.**
If a third embed model with its own instruction-prefix convention (or a different scheme entirely, e.g. `bge`'s single `query:` prefix) gets added later, hardcoding another `if EMBED_MODEL.startswith(...)` branch into `_embed_documents`/`_embed_query` will start to smell. At that point, a small local mapping (e.g. `{"nomic-embed": ("search_document: ", "search_query: "), "bge": ("", "query: ")}`) keyed by model-name prefix would replace the conditional. Not building this now — one gate for one known convention doesn't justify the abstraction yet, and the mapping shape depends on what the second convention actually looks like.

## Risks / Trade-offs

- **[Risk]** Shipping the code change without reindexing leaves prefixed query vectors being compared against unprefixed document vectors already in Chroma — this actively degrades retrieval (queries and documents pushed apart in embedding space, not together), which is worse than the current all-unprefixed baseline. **Mitigation:** `tasks.md` makes `index_v1(reset=True)` a required step in the same change, not a follow-up ticket.
- **[Risk]** `evals/phase1_baseline.md` was captured against the unprefixed index; if left stale, future readers will compare new results against numbers that reflect a different embedding scheme. **Mitigation:** `tasks.md` includes re-running the golden smoke subset and updating that file as part of this change.
- **[Trade-off]** The `startswith("nomic-embed")` gate is a hardcoded string match, not a registry — acceptable per Decision 3, but means someone adding a differently-prefixed model later must remember to touch `_embed_documents`/`_embed_query` again. Flagged explicitly in Decision 4 so it isn't a silent gap.

## Migration Plan

1. Land the `_embed()` / `_embed_documents()` / `_embed_query()` change in `rag.py`.
2. Run `index_v1(reset=True)` (via `cli.py`'s `--reset` flag) to fully rebuild the Chroma collection with prefixed document vectors — a partial/incremental reindex would leave old and new vectors mixed in the same collection.
3. Re-run the golden smoke subset used for `evals/phase1_baseline.md` (at minimum `gq-001` and one `single_doc` item, per the existing `naive-rag` baseline requirement) and update that file's notes to reflect the new embedding scheme.
4. No rollback beyond `git revert` + another `index_v1(reset=True)` against the reverted code — there is no way to keep a mixed-scheme index consistent, so rollback always implies a rebuild in whichever direction.

## Open Questions

- None blocking. The registry idea (Decision 4) is intentionally left open/deferred rather than resolved now.
