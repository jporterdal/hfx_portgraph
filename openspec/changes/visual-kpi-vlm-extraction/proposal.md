## Why

Phase 1's Docling parse pipeline reliably recovers prose and real tables, but annual-report
infographic pages (Sources of Revenue pie, cargo-stats bars, at-a-glance dashboards) encode their
values as chart/icon graphics, not text — Docling emits `<!-- image -->` stubs for them, and a
Marker spike confirmed the values aren't recoverable into Markdown either way (it only exported
usable figure crops). `evals/phase1_baseline.md` and `evals/phase1_parse_gate.md` both flag this
as the top parse-quality gap remaining after Phase 1 exit. This change spikes the local-VLM
extraction path already sketched in `phase-1-parse-rag/design.md` (Decision 1b) so those chart-borne
KPIs become citable facts instead of silent gaps.

## What Changes

- Detect design-heavy / infographic pages in already-parsed Docling output using heuristics
  (figure:text ratio, dashboard-style section titles, missing numeric pairs beside labels) —
  absorbs task 6.1 from `phase-1-parse-rag`.
- Spike figure-crop sourcing for those pages (Docling image export vs Marker JPEG crops vs
  full-page renders) and pick a default input format for the VLM stage — absorbs task 6.2.
- Run a local Ollama vision model against real crops (Sources of Revenue pie + one cargo-stats
  chart from `2023_annual_en`) and produce structured facts (label, value, unit, year, page/figure
  id) — absorbs task 6.3.
- Decide and record whether extracted facts join the existing Phase 1 Chroma index, wait for
  Phase 3 Neo4j Metric nodes, or both — absorbs task 6.4.
- Supersede `phase-1-parse-rag` tasks 6.1–6.4: those checkboxes move to this change; Phase 1 stays
  closed on its own naive-RAG exit criteria regardless of this change's outcome.

This is a spike, not a production feature: the deliverable is a working local extraction path with
citable output and a documented model/format decision, matching the project's local-stack,
learning-first sequencing (`PLAN.md`).

## Capabilities

### New Capabilities
- `visual-kpi-extraction`: design-heavy page detection over Docling parse output, figure-crop
  sourcing, and local Ollama VLM extraction of chart-borne KPIs into a citable `kpi_facts.jsonl`
  sidecar with page/figure provenance.

### Modified Capabilities
(none — `document-parse`, `naive-rag`, and `parent-child-chunking` remain in the
`phase-1-parse-rag` change and haven't been synced to `openspec/specs/` yet; this change adds a
new capability alongside them rather than modifying their requirements.)

## Impact

- **New code**: a page-detection pass over `corpus/parsed/{report_id}/` artifacts; a figure-crop
  extraction step; a VLM extraction script hitting a local Ollama vision model; a `kpi_facts.jsonl`
  sidecar writer.
- **New dependency**: a vision-capable Ollama model (size/accuracy TBD in the spike) in addition to
  the existing `nomic-embed-text` / `llama3.1` models.
- **Possible dependency**: Marker (already optional per `phase-1-parse-rag` design.md) if its
  figure-crop export is chosen over Docling's own image export.
- **No changes** to existing `corpus/parsed/`, `corpus/chunks/`, or `data/chroma/` artifacts unless
  task 6.4's decision is to join facts into the Phase 1 vector index, in which case `rag.py`'s
  indexing path would need a follow-up change.
- **Affected docs**: `docs/phase-1.md` follow-on note or a new `docs/` page once the spike lands.
