## Context

`phase-1-parse-rag` shipped Docling parse + parent-child chunking + naive Ollama RAG and hit its
exit criteria (`evals/phase1_baseline.md`). Its parse-quality gate passed on prose and real tables,
but explicitly flagged one unresolved gap: `2023_annual_en` (and likely other annual reports) loses
chart-/icon-borne KPIs — Sources of Revenue splits, cargo-stats bars, at-a-glance dashboards — to
Docling `<!-- image -->` placeholders. A limited Marker trial (`--mode fast --disable_ocr` on pages
0–12) did not recover those values into Markdown either; it did export usable figure JPEG crops
(e.g. `_page_4_Figure_9.jpeg` retained "41% Cargo / 35% Real Estate" that Docling's placeholder
dropped entirely).

This was deliberately deferred out of Phase 1 exit (`phase-1-parse-rag/design.md` Decision 1b,
tasks 6.1–6.4) as a follow-on spike. This change picks that sketch up as its own scoped unit of
work.

Constraints carried forward from `phase-1-parse-rag`:
- Every claim must be citable to chunk/page (or, here, page/figure).
- Local-stack only — Ollama for any model calls, no cloud VLM APIs.
- Spike-first: PLAN.md's learning sequence favors a working, narrow spike over a general feature.

## Goals / Non-Goals

**Goals:**
- Detect which already-parsed pages are design-heavy/infographic enough that Docling likely lost
  numeric content.
- Get a usable image crop for each such page/figure, sourced from whichever pipeline (Docling
  export, Marker crops, or full-page render) actually produces something a VLM can read.
- Run a local Ollama vision model against at least two real crops — the Sources of Revenue pie and
  one cargo-stats chart from `2023_annual_en` — and get structured, citable facts out.
- Record a clear decision on where those facts live next (Phase 1 vector index, Phase 3 Neo4j
  Metric nodes, both, or neither yet).

**Non-Goals:**
- Corpus-wide VLM rollout across all 8 v1 reports — this spike targets `2023_annual_en` only.
- Replacing Docling as the primary parser for prose/tables.
- A general-purpose chart-to-data extractor; scope is the specific infographic patterns Halifax
  annual reports use (pies, bar dashboards, at-a-glance stat blocks).
- Automated scoring of extraction accuracy — qualitative spot-check against known values (e.g. the
  41%/35% split Marker's crop already confirmed) is enough for this spike.
- Wiring facts into the live RAG index — that's an explicit decision point (task 4 below), not an
  assumed outcome.

## Decisions

### 1. Detection runs as a post-pass over existing Docling parse artifacts, not at parse time
- **Choice:** Read `corpus/parsed/{report_id}/` output (Markdown + page map) that already exists
  from Phase 1 and score pages there, rather than modifying `scripts/parse_corpus.py`.
- **Why:** Keeps this spike additive and reversible — no risk to the working Phase 1 parse path;
  reuses artifacts already on disk for all 8 reports.
- **Alternatives:** Detect during parsing (tighter loop, but couples an unproven heuristic to the
  stable Phase 1 parser); detect on raw PDF pages directly (loses Docling's existing figure/text
  block counts, which are a natural heuristic input).

### 2. Detection heuristics: figure density + low text density + dashboard-style headings
- **Choice:** Flag a page as design-heavy if it has a high ratio of picture/figure blocks or
  `<!-- image -->` stubs to body-text tokens, and/or its section heading matches a dashboard
  pattern ("at-a-glance", "sources of revenue", "cargo stats") with numeric labels but no adjacent
  values in the Markdown.
- **Why:** Matches the concrete failure Marker's spike already confirmed (values present in the
  image, absent in text) rather than a generic image-density threshold that would also flag
  unrelated content (e.g. photos in narrative sections).
- **Alternatives:** Pure image-count threshold (too many false positives on photo-heavy narrative
  pages); manual page allowlist (fast for one report, doesn't generalize — acceptable fallback if
  heuristics prove unreliable in the spike).

### 3. Figure-crop source: prefer Docling image export, fall back to Marker crops or page renders
- **Choice:** Try Docling's own exported image bytes first for a flagged page/figure; if Docling
  only emitted a placeholder with no image, fall back to Marker's JPEG crop (already spiked and
  confirmed to retain chart values) or a full-page render via `pypdfium2` as a last resort.
- **Why:** Avoids adding Marker as a hard dependency for every design-heavy page when Docling
  already has the bytes; Marker crops are proven only for the pages already spiked.
- **Alternatives:** Marker-only crop pipeline (simpler, but reintroduces Marker's `--disable_ocr`
  text-layer dependency corpus-wide); full-page renders only (loses precision — VLM sees
  surrounding clutter, not just the target figure).

### 4. VLM host: local Ollama, model TBD in-spike
- **Choice:** Run extraction through the same local Ollama daemon already used for embeddings/chat
  in Phase 1, using a vision-capable model. Model choice (size vs bar/pie-reading accuracy) is an
  explicit open question this spike resolves empirically rather than upfront.
- **Why:** Keeps the whole pipeline on one local model host; avoids introducing a second inference
  stack. Distinct from Marker/Surya's own `llama-server` OCR dependency — this uses the Ollama
  daemon Phase 1 already depends on.
- **Alternatives:** Cloud VLM API (fastest to get signal, violates local-stack constraint); a
  dedicated vision pipeline (llama.cpp multimodal, etc.) — more setup for a spike that just needs a
  yes/no on local feasibility.

### 5. Output shape: `kpi_facts.jsonl` sidecar, not a live index write
- **Choice:** Extraction writes structured facts (`label`, `value`, `unit`, `year`, `report_id`,
  `page`, `figure_id`) to a new `corpus/kpi_facts/{report_id}.jsonl` sidecar, mirroring the
  `corpus/chunks/` layout. Whether these facts get embedded into `data/chroma/` or wait for Phase 3
  Neo4j Metric nodes is decided at the end of the spike (task 4), not assumed now.
- **Why:** Matches the existing artifact-layout convention (`phase-1-parse-rag/design.md` Decision
  3); keeps the spike's output inspectable and diffable before committing to an integration path.
- **Alternatives:** Extract straight into Chroma (couples an unvalidated extraction step to the
  live RAG index); extract straight into a Neo4j Metric schema (pulls Phase 3 forward before its
  ontology is designed).

## Risks / Trade-offs

- **[Risk] Detection heuristics are unreliable (miss real infographics or flag false positives)**
  → Mitigation: spike against `2023_annual_en` only, spot-check by eye against pages already known
  to have chart-borne KPIs (Sources of Revenue, cargo stats) before trusting the heuristic more
  broadly.
- **[Risk] Local vision models underperform on bar/pie chart reading** → Mitigation: qualitative
  check against the known 41%/35% split already recovered via Marker's crop as a ground-truth
  spot-check; if no local model clears that bar, record the negative result and stop rather than
  forcing an integration decision.
- **[Risk] Figure crops from Docling are lower quality than Marker's** → Mitigation: Decision 3's
  fallback chain; compare both sources on the same page during the spike before picking a default.
- **[Trade-off] Spike scope is one report, two figures** → Faster signal, but corpus-wide coverage
  and cost/latency at scale remain unknown until a follow-on change, if this spike succeeds.
- **[Trade-off] Facts sidecar stays disconnected from RAG/graph until task 4's decision** → Slower
  path to user-visible value, but avoids polluting the working Phase 1 index with unvalidated
  extraction output.

## Migration Plan

1. Build the design-heavy detector over existing `corpus/parsed/2023_annual_en/` artifacts.
2. Spike figure-crop sourcing (Docling export vs Marker vs page render) on the same report.
3. Run a local Ollama vision model against the Sources of Revenue + one cargo-stats crop; write
   `corpus/kpi_facts/2023_annual_en.jsonl`.
4. Record the integration decision (task 4) in this design doc or the proposal, updating both if
   the outcome changes scope.

Rollback: delete `corpus/kpi_facts/`; no changes to `corpus/parsed/`, `corpus/chunks/`, or
`data/chroma/` unless task 4 explicitly decides to write into them, in which case rollback extends
to reverting that follow-up change.

## Spike Results (2026-08-22)

Ran the full pipeline against `2023_annual_en` (`scripts/spike_kpi_detect.py`,
`scripts/spike_kpi_crops.py`, `scripts/spike_kpi_extract.py`). Full command sequence and outcome
notes: `evals/kpi_vlm_spike.md`.

- **Detection:** heading-keyword + figure-density heuristic flagged pages 4, 5, 6, 7 in
  `2023_annual_en`, including the required Sources of Revenue (5) and Cargo Stats (6) pages, with
  no false positives on financial-statement or narrative pages.
- **Crop sourcing:** Docling image export (`generate_picture_images=True`) produced usable,
  precise per-figure crops for both target pages — as good as or better than the earlier Marker
  spike crops — so Marker was not needed for the two required figures. A "flat-graphic" filter
  (mostly-white OR few-dominant-colors, above an area floor) reliably separated real chart crops
  from decorative icons and photos, with one calibration fix needed for a colored-background map
  chart (see below).
- **VLM extraction:** `qwen2.5vl:7b` (pulled locally via Ollama — chosen for chart/infographic
  reading strength over `llava`/`moondream`) correctly read the Sources of Revenue chart
  (41% Cargo / 35% Real Estate / 12% Cruise / 9% / 3%, matching the Marker-spike ground truth
  exactly) and the Cargo Stats pie (91%/9%, matching `4,209,781 / 4,613,423 MT` from text),
  producing citable `label/value/unit/year/report_id/page/figure_id` facts.
- **Two real failure modes found and fixed during the spike, not just anticipated:**
  1. The crop-source fallback initially accepted a non-chart-like Marker photo (a container-ship
     picture with no numbers on it) when Docling had nothing better; the VLM didn't refuse — it
     quietly answered from unrelated page text instead, producing plausible-looking but ungrounded
     facts with wrong labels. Fixed by only falling through to Marker when a candidate actually
     passes the chart-like filter, otherwise going to a full-page render (which legitimately
     contains the same numbers as visible pixels).
  2. The initial extraction prompt let page context text override chart values outright (the model
     read tonnage figures from body text instead of the pie chart's own 91%/9%). Fixed by
     instructing the model that `value`/`unit` must come only from the image, while `text` may
     still be used to word a `label` for slices with no on-image text of their own.
- **Outcome: PASS** — both required scenarios (Sources of Revenue, one cargo-stats page) produced
  correct, citable facts. `corpus/kpi_facts/2023_annual_en.jsonl` written; `corpus/parsed/`,
  `corpus/chunks/`, and `data/chroma/` untouched.

## Decision 6: Integration path — wait for Phase 3 Neo4j Metric nodes, don't join Phase 1 Chroma now

- **Choice:** `kpi_facts.jsonl` stays a disconnected sidecar. Do not embed synthesized fact
  sentences into the Phase 1 Chroma index; wait for Phase 3's Neo4j Metric-node schema to ingest
  these facts directly.
- **Why:** The fact shape (`label`, `value`, `unit`, `year`, `report_id`, `page`, `figure_id`) is
  already typed/structured — a natural fit for graph Metric nodes, not for semantic-embedding
  retrieval, which would require lossy text-ification first (e.g. "In 2023, Cargo was 41% of
  Sources of Revenue (page 5)."). More importantly, this spike surfaced real fragility along the
  way (crop-selection had to be corrected once a bad fallback was found; extraction prompt had to
  be corrected once after it silently pulled values from the wrong source) on a four-page,
  one-report sample — not yet enough validated accuracy to justify writing into the live,
  already-passing Phase 1 index. A corpus-wide accuracy pass is a prerequisite for any live-index
  integration, and is out of scope here (see Non-Goals).
- **Alternatives considered:** Join Phase 1 Chroma now (rejected — couples unvalidated,
  small-sample extraction to the working naive-RAG index ahead of broader validation); do both
  now (rejected for the same reason, plus doubles integration work before Phase 3's Metric schema
  even exists to check shape-fit against); do neither ever (rejected — the fact shape is
  deliberately Metric-node-ready, so Phase 3 is a concrete, near-term consumer, not an open-ended
  deferral).
- **Follow-up scope:** None opened in this change (per task 4.3, only required if the decision was
  "join Phase 1 index now"). Wiring `kpi_facts` into Neo4j Metric nodes belongs to the Phase 3
  change, once its ontology exists to check the fit against.

## Open Questions

- Which local Ollama vision model to use — resolved empirically during the spike, not upfront.
- Whether design-heavy detection should eventually run at parse time (folded into
  `scripts/parse_corpus.py`) once heuristics are validated, versus staying a separate post-pass.
- Whether `kpi_facts` join the Phase 1 vector index, wait for Phase 3 Metric nodes, or both — the
  explicit decision point this spike exists to answer.
- Whether corpus-wide rollout (beyond `2023_annual_en`) is worth a follow-up change once this spike
  proves (or disproves) local VLM feasibility.
