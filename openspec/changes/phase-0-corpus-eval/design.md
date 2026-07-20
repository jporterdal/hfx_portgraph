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
- Cloudflare bypass stacks (Playwright clearance flows, FlareSolverr, TLS impersonation, residential proxies) for Phase 0
- Live HTML scraping of the reports page as the acquisition source of truth

## Decisions

### 1. Corpus layout: `corpus/raw/` + `corpus/manifest.yaml`
- **Choice:** Store original PDFs under `corpus/raw/` with stable filenames; describe them in YAML manifest.
- **Why:** Manifest is human-editable and git-friendly; binaries may be gitignored or LFS later.
- **Alternatives:** JSONL-only inventory (harder to skim); SQLite (overkill for dozens of files).

### 2. Filename convention
- **Choice:** `{year}_{report_type}_{lang}.pdf` where `report_type` is one of `annual`, `financials`, `other` and `lang` is `en` / `fr` / `unknown`.
- **Why:** Predictable joins from eval items → files without opaque UUIDs.
- **Alternatives:** Keep publisher filenames only (fragile); content-hash names (opaque for learning).

### 3. Acquisition: curated URLs → live PDF attempt → Wayback → manual browser
- **Choice:** Three-tier acquisition. (1) Maintain a curated URL catalog of known annual/financials PDF URLs (from Wayback inventory / browser confirmation). (2) `scripts/fetch_corpus.py` tries each live `porthalifax.ca` PDF URL, then a Wayback rewrite if live fails (e.g. Cloudflare 403). (3) Document manual browser download into `corpus/raw/` with the stable filename convention; re-run manifest/checksum steps. Do **not** scrape the live reports HTML as the primary mechanism.
- **Why:** Live site and direct PDF URLs often return Cloudflare challenges to automated clients; Wayback already provided a usable inventory snapshot; Phase 0 success is a complete local corpus + manifest, not scraper resilience.
- **Alternatives considered:** Live HTML scrape with BeautifulSoup (blocked by CF); Playwright/FlareSolverr bypass (fragile, ToS-grey, overkill); fully manual-only (slower but acceptable as the final tier).

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

- **[Risk] Cloudflare blocks automated clients on live HTML and PDF URLs** → Mitigation: curated catalog + Wayback fetch; manual browser drop is a first-class success path; never block Phase 0 on CF bypass.
- **[Risk] Reports page HTML/PDF URLs change or newest years missing from Wayback** → Mitigation: manifest stores `source_url` + optional checksum; README documents browser download for post-snapshot years (e.g. 2024–2025).
- **[Risk] Incomplete year coverage or missing French editions** → Mitigation: manifest records gaps explicitly (`status: missing`); golden set tags `bilingual` only when both languages exist.
- **[Risk] Golden questions without page hints become unusable after bad parsing** → Mitigation: require `expected_evidence.years` always; prefer `page_hint` or section title when known from skimming PDFs.
- **[Risk] Writing gold answers that later LLMs copy-match wrongly grades style** → Mitigation: emphasize evidence fields over polished answer prose in Phase 0.
- **[Trade-off] Curated catalog over live scrape** → Catalog can drift; cheaper than maintaining a CF-resistant scraper for dozens of public PDFs.

## Migration Plan

N/A for production deploy. Rollout within the repo:
1. Create directories and ignore rules
2. Populate corpus + manifest
3. Author golden JSONL
4. Verify exit checklist (counts, tags, hard cases)
5. Hand off to Phase 1a parse spike using 1 annual + 1 financials PDF from the inventory

Rollback: delete `corpus/raw/` locally; revert committed manifest/evals if needed.

## Open Questions

- Whether 2024–2025 annual/financials (post-dating the Dec 2024 Wayback snapshot) are required for Phase 0 v1 or deferred until browser confirmation
- Exact handling of the 2020 annual report if it is HTML flipbook-only rather than a direct PDF
- Minimum year range for v1 beyond the documented 2020–2023 core targets (e.g. include 2019 and earlier historical financials?)
