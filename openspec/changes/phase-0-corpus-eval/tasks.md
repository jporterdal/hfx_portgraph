## 1. Repo layout and ignore rules

- [ ] 1.1 Create `corpus/raw/`, `corpus/README.md` placeholder, and `evals/` directories
- [ ] 1.2 Add `corpus/raw/*.pdf` to `.gitignore` (keep `corpus/manifest.yaml` and READMEs trackable)
- [ ] 1.3 Add a minimal Python project stub if needed for the download script (`pyproject.toml` or `requirements.txt` with `httpx`/`beautifulsoup4` as chosen)

## 2. Corpus acquisition

- [ ] 2.1 Inventory the live reports page and list available years/types/languages in notes (paste into `corpus/README.md`)
- [ ] 2.2 Implement `scripts/fetch_corpus.py` (or equivalent) to download PDFs into `corpus/raw/` using the `{year}_{report_type}_{lang}.pdf` naming convention
- [ ] 2.3 Run acquisition for annual + consolidated financials across available years; fall back to documented manual download for any brittle links
- [ ] 2.4 Write `corpus/manifest.yaml` with `id`, `year`, `report_type`, `language`, `source_url`, `filename`, `status` for every present (and known-missing) entry
- [ ] 2.5 Optionally record checksums (`sha256`) in the manifest for each `status: present` file
- [ ] 2.6 Finish `corpus/README.md` with rebuild steps (script usage + manual fallback)

## 3. Golden eval set

- [ ] 3.1 Create `evals/README.md` describing schema, controlled tags, and size/hard-case gates
- [ ] 3.2 Add JSON schema or example record documenting required fields (`id`, `question`, `tags`, `expected_evidence`, `notes`)
- [ ] 3.3 Author the flagship multi-year question (container throughput + operating income 2020–2023 + initiative drivers) with evidence hints
- [ ] 3.4 Author at least 10 additional golden items spanning `single_doc`, `yoy_metric`, `narrative`, and `multi_hop`
- [ ] 3.5 Expand to 20–40 total items; ensure ≥80% have controlled tags
- [ ] 3.6 Add ≥1 `table_heavy` and ≥1 `year_collision` hard case; add `bilingual` item or document bilingual gap in `evals/README.md`
- [ ] 3.7 Cross-check `expected_evidence` report/filename hints against `corpus/manifest.yaml` ids/filenames

## 4. Validation and Phase 0 exit

- [ ] 4.1 Write a small validator script (or checklist commands) that checks: manifest filenames resolve, golden JSONL parses, item count in [20,40], tag rate ≥80%, hard-case tags present
- [ ] 4.2 Run the validator and fix any failures
- [ ] 4.3 Record Phase 0 exit note in `evals/README.md` or `corpus/README.md`: year coverage summary + pointer to the two PDFs recommended for Phase 1a parse spike (one annual, one financials)
