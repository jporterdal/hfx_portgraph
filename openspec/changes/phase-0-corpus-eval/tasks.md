## 1. Repo layout and ignore rules

- [x] 1.1 Create `corpus/raw/`, `corpus/README.md` placeholder, and `evals/` directories
- [x] 1.2 Add `corpus/raw/*.pdf` to `.gitignore` (keep `corpus/manifest.yaml` and READMEs trackable)
- [x] 1.3 Add a minimal Python project stub if needed for the download script (`pyproject.toml` or `requirements.txt` with `httpx`/`beautifulsoup4` as chosen)

## 2. Corpus acquisition

- [x] 2.1 Inventory the live reports page and list available years/types/languages in notes (paste into `corpus/README.md`)
- [x] 2.2 Add a curated URL catalog for v1 annual/financials targets and implement `scripts/fetch_corpus.py` to save into `corpus/raw/` with `{year}_{report_type}_{lang}.pdf` naming: try live PDF URL, then Wayback rewrite; do not require live HTML scraping
- [x] 2.3 Run acquisition for annual + consolidated financials across catalog years; leave gaps for manual browser download when live and Wayback both fail (acceptable in CF-blocked agent/CI environments)
- [x] 2.4 Write `corpus/manifest.yaml` with `id`, `year`, `report_type`, `language`, `source_url`, `filename`, `status` for every present (and known-missing) entry
- [x] 2.5 Optionally record checksums (`sha256`) in the manifest for each `status: present` file
- [x] 2.6 Finish `corpus/README.md` with three-tier rebuild steps: curated catalog / script (live→Wayback), then manual browser drop + manifest refresh



## 3. Golden eval set

- [x] 3.1 Create `evals/README.md` describing schema, controlled tags, and size/hard-case gates
- [x] 3.2 Add JSON schema or example record documenting required fields (`id`, `question`, `tags`, `expected_evidence`, `notes`)
- [x] 3.3 Author the flagship multi-year question (container throughput + operating income 2020–2023 + initiative drivers) with evidence hints
- [x] 3.4 Author at least 10 additional golden items spanning `single_doc`, `yoy_metric`, `narrative`, and `multi_hop`
- [x] 3.5 Expand to 20–40 total items; ensure ≥80% have controlled tags
- [x] 3.6 Add ≥1 `table_heavy` and ≥1 `year_collision` hard case; add `bilingual` item or document bilingual gap in `evals/README.md`
- [x] 3.7 Cross-check `expected_evidence` report/filename hints against `corpus/manifest.yaml` ids/filenames

## 4. Validation and Phase 0 exit

- [x] 4.1 Write a small validator script (or checklist commands) that checks: manifest filenames resolve, golden JSONL parses, item count in [20,40], tag rate ≥80%, hard-case tags present
- [x] 4.2 Run the validator and fix any failures
- [x] 4.3 Record Phase 0 exit note in `evals/README.md` or `corpus/README.md`: year coverage summary + pointer to the two PDFs recommended for Phase 1a parse spike (one annual, one financials)