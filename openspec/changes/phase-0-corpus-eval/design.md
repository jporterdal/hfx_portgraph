## Context

`hfx_portgraph` is greenfield: architecture lives in `PLAN.md`, but there is no corpus, eval harness, or application code yet. Phase 0 establishes the teaching corpus (Port of Halifax public reports) and a golden Q&A set so later phases can measure retrieval and agent quality instead of demo-ing against ad-hoc questions.

Source of reports: https://www.porthalifax.ca/about-us/port-authority/reports/

Constraints from the architecture plan:
- Learning-first; no LangGraph / Neo4j / embeddings in this phase
- Eval mindset before infrastructure
- Hard failure modes (tables, bilingual, year collisions) must appear in the golden set

## Goals / Non-Goals

**Goals:**
- Local, reproducible inventory of Port Authority PDFs with metadata
- Golden eval set of 20–40 items with evidence hints and query-type tags
- Clear exit criteria so Phase 1a (parse spike) can begin against known docs and questions

**Non-Goals:**
- PDF parsing, chunking, embeddings, or vector stores
- LangGraph agent loops or Neo4j
- Automated answer scoring / LLM-as-judge
- Full bilingual parallel corpora if French editions are sparse (document gaps instead)
- Polished report UX or product packaging

## Decisions

### 1. Corpus layout: `corpus/raw/` + `corpus/manifest.yaml`
- **Choice:** Store original PDFs under `corpus/raw/` with stable filenames; describe them in YAML manifest.
- **Why:** Manifest is human-editable and git-friendly; binaries may be gitignored or LFS later.
- **Alternatives:** JSONL-only inventory (harder to skim); SQLite (overkill for dozens of files).

### 2. Filename convention
- **Choice:** `{year}_{report_type}_{lang}.pdf` where `report_type` is one of `annual`, `financials`, `other` and `lang` is `en` / `fr` / `unknown`.
- **Why:** Predictable joins from eval items → files without opaque UUIDs.
- **Alternatives:** Keep publisher filenames only (fragile); content-hash names (opaque for learning).

### 3. Acquisition: scripted download with manual fallback
- **Choice:** Small Python script (or documented curl steps) that fetches linked PDFs from the reports page into `corpus/raw/` and upserts manifest entries. Manual download is acceptable if scraping is brittle.
- **Why:** Site structure may change; Phase 0 success is inventory completeness, not scraper elegance.
- **Alternatives:** Fully manual download only (slower, error-prone); headless browser scrape (heavy for this phase).

### 4. Golden set format: JSONL
- **Choice:** `evals/golden.jsonl` — one JSON object per line.
- **Why:** Easy to append, stream, and load in later eval scripts; diffs stay reviewable.
- **Alternatives:** YAML list (fine for small N but noisier diffs); CSV (weak for nested evidence fields).

### 5. Required golden fields
Each item MUST include:
- `id` (stable string)
- `question`
- `tags` (subset of: `single_doc`, `yoy_metric`, `narrative`, `multi_hop`, `table_heavy`, `bilingual`, `year_collision`)
- `expected_evidence` with at least: `years`, optional `metrics`, optional `entities`, optional `report_ids` / filename hints, optional `page_hint`
- `notes` (free text: what a correct answer must ground on; not a full gold answer string unless easy)

- **Why:** Later phases need *evidence shape* more than a single canonical sentence; financial wording varies.
- **Alternatives:** Full gold answers only (brittle); RAGAS-style datasets (premature).

### 6. Target coverage
- **Choice:** 20–40 items; ≥80% tagged; ≥3 deliberately hard cases covering table-heavy, bilingual (if available), and year-label collision.
- **Why:** Matches PLAN.md Phase 0 and explore-session exit criteria.
- **Alternatives:** 100+ items (too slow before any system exists); <15 (weak baseline).

### 7. v1 corpus scope
- **Choice:** Prefer annual reports and consolidated financials across available years; include other report types in the manifest if present but do not block Phase 0 on them.
- **Why:** Flagship eval query (throughput + operating income + initiatives) lives in those doc types.

### 8. Git policy for PDFs
- **Choice:** Add `corpus/raw/*.pdf` to `.gitignore` by default; commit `manifest.yaml` and a short `corpus/README.md` describing how to fetch. Optionally document checksums in the manifest for integrity.
- **Why:** Keeps the repo small; rebuildable from public URLs.
- **Alternatives:** Commit PDFs (convenient but heavy); Git LFS (extra setup for Phase 0).

## Risks / Trade-offs

- **[Risk] Reports page HTML/PDF URLs change** → Mitigation: manifest stores source URL + optional checksum; script failures fall back to manual download instructions in `corpus/README.md`.
- **[Risk] Incomplete year coverage or missing French editions** → Mitigation: manifest records gaps explicitly (`status: missing`); golden set tags `bilingual` only when both languages exist.
- **[Risk] Golden questions without page hints become unusable after bad parsing** → Mitigation: require `expected_evidence.years` always; prefer `page_hint` or section title when known from skimming PDFs.
- **[Risk] Writing gold answers that later LLMs copy-match wrongly grades style** → Mitigation: emphasize evidence fields over polished answer prose in Phase 0.
- **[Trade-off] Skipping automated download polish** → Faster start; may revisit scraper in a later chore change.

## Migration Plan

N/A for production deploy. Rollout within the repo:
1. Create directories and ignore rules
2. Populate corpus + manifest
3. Author golden JSONL
4. Verify exit checklist (counts, tags, hard cases)
5. Hand off to Phase 1a parse spike using 1 annual + 1 financials PDF from the inventory

Rollback: delete `corpus/raw/` locally; revert committed manifest/evals if needed.

## Open Questions

- Exact set of `report_type` values beyond `annual` / `financials` / `other` once the live page is inventoried
- Whether any PDFs are behind non-direct links requiring manual save
- Minimum year range for v1 (e.g. 2019–2024 vs all available)
