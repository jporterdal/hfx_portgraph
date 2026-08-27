# hfx_portgraph — Architecture Plan

Explore pass on stack, RAG strategy, and phased learning path for an open-source agentic report system (LangGraph + Neo4j + Ollama) over the Port of Halifax public reports corpus.

## Verdict

Direction is strong and well-scoped for learning. **Keep LangGraph, Ollama, and Neo4j.** Replace LlamaParse if you want a fully open-source stack. Prefer **hybrid retrieval** (parent-child chunks + a lean entity graph) over jumping straight to full GraphRAG.

| Decision | Call |
|---|---|
| LangGraph + Ollama | Keep |
| Neo4j (phased) | Keep |
| LlamaParse → OSS parser | Swap |
| Parent-child + schema graph | Hybrid |

## Why this project fits

Port Authority annual reports and consolidated financials are a strong teaching corpus: multi-year continuity, tables + narrative, recurring entities (terminals, projects, cargo metrics, debt, CapEx), and questions that need planning and multi-hop retrieval rather than single similarity search.

**Good evaluation query example:** How did container throughput and operating income move from 2020–2023, and what strategic initiatives were cited as drivers? (Forces temporal join + narrative grounding + sufficiency loops.)

**Hard failure modes to design for:** Table OCR/layout drift, bilingual docs, year-label collisions, and LLM-invented Cypher against Neo4j. Treat these as first-class tests.

**Corpus source:** https://www.porthalifax.ca/about-us/port-authority/reports/

## Tech stack — reinforce or replace

| Layer | Tentative pick | Call | Notes / alternatives |
|---|---|---|---|
| Orchestration | LangGraph | Keep | Best match for deterministic plan → retrieve → critique → report loops. Alts: LlamaIndex Workflows, Haystack Agents. |
| Graph DB | Neo4j | Keep | Cypher ecosystem. Lighter local start: FalkorDB or NetworkX, then graduate to Neo4j. |
| Local LLM | Ollama + Llama 3.1 | Keep | Prefer larger models for extraction/planning if hardware allows; smaller for routing. Alts: LM Studio, llama.cpp, vLLM. |
| Embeddings | (unspecified) | Add | Use `nomic-embed-text` or `bge-m3` via Ollama. Neo4j vector index and/or Qdrant/Chroma. |
| Ingestion | LlamaParse | Swap | Cloud/API, not fully OSS. Prefer Docling, Marker, Unstructured (local), MinerU, or PyMuPDF + custom table extract. |
| Vector store | Neo4j only | Optional | Neo4j vectors work; Qdrant helps for hybrid BM25+dense experiments. |

**Open-source purity gap:** LlamaParse is the main conflict with “run entirely on open-source models/tools.” Keep the same pipeline shape; swap the parser.

### Revised default stack

LangGraph · Neo4j (graph + vector) · Ollama (Llama 3.1 + nomic-embed) · Docling · Python · optional Qdrant later · Port of Halifax PDF corpus

## Recommended system shape

Two pipelines: offline corpus build, online LangGraph report agent.

### Offline ingestion

```
[Raw PDF] → [Docling/Marker] → [Markdown + tables]
  → [Hierarchical chunks: parent section / child passage]
  → [Constrained LLM entity+relation extract]
  → [Neo4j: Document–Section–Chunk–Entity–Metric–Year]
```

### Online LangGraph state machine

```
parse_query → write_plan → retrieve (graph + vector tools)
  → evaluate_sufficiency → (loop: refine plan / new tools)
  → synthesize insights → compile_report → cite sources
```

| Node | Role |
|---|---|
| Planner | Decompose the question into evidence goals (metrics, years, entities) without retrieving yet. |
| Retriever | Prefer typed tools (by year, by metric, by entity) over free-form Cypher from a small model. |
| Critic | Score coverage vs plan; set missing slots; enforce max iterations and explicit “I don’t know” exits. |

## Parent-child vs GraphRAG

These are complementary, not mutually exclusive. For Halifax reports, start hierarchical, then layer a small schema-driven graph—not a full Microsoft-style community GraphRAG build on day one.

| Approach | Teaches | Best for | Cost / risk |
|---|---|---|---|
| Parent-child chunking | Context windows, citation, hierarchical retrieval | “What did the 2022 annual report say about…?” | Low — phase 1 |
| Schema GraphRAG (Neo4j) | Entities, Cypher, multi-hop joins | YoY metrics, initiative→outcome links | Medium — needs ontology + eval set |
| Community GraphRAG (MS-style) | Global summarization over huge corpora | Very large, messy knowledge bases | High — overkill for ~dozens of PDFs |

**Recommended learning path:** Phase A parent-child + hybrid search → Phase B fixed ontology into Neo4j (Organization, Report, Year, Metric, Project, Terminal, Initiative) → Phase C LangGraph tools over both layers with sufficiency loops.

## Ingestion pipeline — keep shape, harden pieces

| Stage | Original idea | Suggestion |
|---|---|---|
| Parse | LlamaParse → Markdown | Docling or Marker → Markdown + structured tables (preserve page/section IDs) |
| Chunk | Markdown chunks | Parent = H2/H3 section; child = 300–800 token passages with `parent_id` + page refs |
| Extract | LLM IE → Neo4j | JSON-schema / constrained decoding; validate before write; provenance to chunk IDs |
| Store | Neo4j only | Graph for entities/metrics + vector index on chunks; keep raw markdown for citations |

Extraction quality with Llama 3.1 8B will be the bottleneck. Prefer a larger local model for offline IE, or extract metrics with table parsers first and only use the LLM for narrative relations.

## Alternatives worth knowing

- **Orchestration:** LlamaIndex Workflows (batteries-included indexes); Haystack (strong pipelines); CrewAI/AutoGen (chatty multi-agent — worse fit for deterministic reports).
- **Graph / RAG:** Neo4j LLM Graph Builder / LangChain Neo4j; LightRAG / Graphiti; Microsoft GraphRAG (heavy for this corpus size).
- **Local inference:** Ollama for DX; vLLM/llama.cpp when bulk extraction needs throughput; keep embeddings local.
- **Parsing:** Docling (strong OSS PDF→structure); Marker (Markdown fidelity); Unstructured local partitioners as fallback.

## Phased build plan (learning-first)

| Phase | Ship | Learning outcome |
|---|---|---|
| 0 | Scrape Halifax reports; inventory years/types; golden Q&A set (20–40) | Corpus hygiene + eval mindset |
| 1 | OSS parse + parent-child + Ollama naive RAG | Chunking, embeddings, citations |
| 2 | LangGraph: plan → retrieve → critique → answer (no Neo4j yet) | Deterministic agent loops |
| 3 | Ontology + Neo4j load; typed Cypher/tools | Graph modeling + safe tool use |
| 4 | Hybrid tools + report compiler with source trail | End-to-end agentic research system |

### Phase 3 note — semantic-interpretation gaps carried forward from `strip-page-furniture`

`strip-page-furniture` (Phase 1 corpus-quality fix, landed 2026-08-27) hit three ambiguities its
bbox-position/text-repetition/Docling-label signals could not resolve, because resolving them means
reading what the text *means*, not where it sits or whether it repeats. Phase 3's "Constrained LLM
entity+relation extract" step is the first point in this roadmap where the pipeline reads chunk
content for meaning rather than only embedding it for similarity — flagged here so these don't get
rediscovered as new problems once that capability exists:

1. **Furniture-vs-real-content tie-breaking on meaning, not position.**
   `openspec/changes/strip-page-furniture/design.md` Decision 1's "Known accepted false positive"
   (the Africville Museum photo caption, stripped because it shares a furniture position band with
   unrelated page numbers) and its "Future work — semantic tie-breaker" section: the only thing
   separating that caption from real furniture is that its own text *describes an image*
   ("Pictured: the Africville Museum...") — a self-reference no bbox/repetition/label signal sees.
2. **Cross-document templated boilerplate as a potential positive signal, not noise.** Same
   design.md's "Known intentional gap" section: near-identical boilerplate sentences (e.g. "Certain
   of the comparative figures for {year} have been reclassified...") recur once per report across
   several documents, and are deliberately left unstripped — two notes in different reports sharing
   near-identical phrasing is itself a signal they're the same disclosure type, a feature a future
   entity/relation extraction pass could exploit rather than something a furniture detector fights.
3. **Heading-to-content semantic scoping across structural boundaries.** `2021_annual_en`'s "PORT OF
   HALIFAX BY THE NUMBERS" page introduces several stat-card infographics, but Docling gives each
   card (e.g. "4,902,894 Total Cargo in Metric Tonnes") its own sibling heading instead of nesting it
   under the dashboard title — so the chunk holding "1,100 Commercial Cargo Vessels / 150 Countries /
   19 Container Lines" carries none of the context tying it back to "by the numbers." Recognizing
   that link requires understanding what "by the numbers" *means* in relation to a page of stat
   callouts, not heading depth or page proximity — no signal in `parse.py`/`chunk.py` catches this.

None of these were pursued in Phase 1 — see `strip-page-furniture/design.md`'s "Rejected alternative
— learned classifier" for why (no hand-labeled ground truth exists yet to train or validate against).
Revisit once Phase 3's extraction step exists: the same read that pulls entities/metrics out of a
chunk could plausibly also judge these, since all three need the same capability — real content read
for meaning, with page/document context, not just position or repetition.

## Design decisions to lock early

1. Fixed ontology before free extraction
2. Typed retrieval tools, not raw Cypher from the LLM
3. Max loop N + explicit insufficiency
4. Every claim cites chunk/page

These prevent the usual GraphRAG demo collapse: hallucinated schema, runaway tool loops, and uncited financial claims.

## Related artifacts

- Interactive canvas (Cursor): `canvases/rag-agent-architecture-brainstorm.canvas.tsx` (also mirrored under this repo’s `canvases/` for reference)
- Original explore session lived in the home/empty-window workspace before this move
