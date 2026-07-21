# Port of Halifax report corpus

Local inventory of public Port Authority reports used by `hfx_portgraph`.

**Source (live):** https://www.porthalifax.ca/about-us/port-authority/reports/  
**French UI path:** https://www.porthalifax.ca/a-propos-de-nous/administration-portuaire/rapports/?lang=fr  
**Inventory snapshot:** [Wayback Machine, 2024-12-14](https://web.archive.org/web/20241214192351/https://www.porthalifax.ca/about-us/port-authority/reports/)

> **Note:** Live `porthalifax.ca` PDF URLs often return Cloudflare challenges to automated clients. Many PDF binaries are **not** archived on Wayback (only the HTML reports page is). Prefer a normal browser for the final download step.

## Layout

| Path | Purpose |
|---|---|
| `raw/` | Original PDF binaries (gitignored) |
| `catalog.yaml` | Curated v1 URL list (committed) |
| `manifest.yaml` | Per-report status, paths, checksums (committed) |

## Filename convention

`{year}_{report_type}_{lang}.pdf`

- `report_type`: `annual` | `financials` | `other`
- `lang`: `en` | `fr` | `unknown`

## Rebuild (three-tier)

### 1. Curated catalog + script (live → Wayback)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .   # or: pip install httpx pyyaml
python scripts/fetch_corpus.py
```

The script reads `corpus/catalog.yaml`, tries each live `source_url`, then Wayback candidates (fixed snapshot + availability API). On success it writes `corpus/raw/{year}_{type}_{lang}.pdf` and refreshes `manifest.yaml` (including `sha256`).

Re-scan local files without downloading:

```bash
python scripts/fetch_corpus.py --manifest-only
```

### 2. Manual browser fallback (expected in CF-blocked environments)

1. Open https://www.porthalifax.ca/about-us/port-authority/reports/ in a browser.
2. Download annual + consolidated financials PDFs for the years in `catalog.yaml` into any folder (e.g. `~/Downloads`). Keep the publisher filenames.
3. Map them into `corpus/raw/` (dry-run first):

```bash
python scripts/map_corpus_filenames.py ~/Downloads            # preview
python scripts/map_corpus_filenames.py ~/Downloads --apply    # copy into corpus/raw/
python scripts/map_corpus_filenames.py --print-map            # show publisher → corpus names
```

4. Refresh the manifest:

```bash
python scripts/fetch_corpus.py --manifest-only
```

### 3. Verify

```bash
python scripts/validate_phase0.py
```

## Inventory notes (Phase 0 / task 2.1)

Observed on the English reports page (via Wayback + search snippets). **v1 priority = annual + consolidated financials.**

### Core v1 targets (English)

| Year | Type | Language | Notes / known source URL |
|---|---|---|---|
| 2023 | annual | en | `.../2024/05/WEB-medium-res-Port-ENGLISH-2023-AnnualReport-May29-2024.pdf` |
| 2023 | financials | en | `.../2024/04/HPAFinancialStatements2023-FINAL-ENG.pdf` |
| 2022 | annual | en | `.../2024/03/HPA-Annual-Report-2022-ENG.pdf` |
| 2022 | financials | en | `.../2024/05/HPA-Financials-December-31-2022.pdf` |
| 2021 | annual | en | `.../2022/05/HPA_Annual_Report_2021.pdf` |
| 2021 | financials | en | `.../2022/04/FINAL-HPA-2021-FS.pdf` |
| 2020 | annual | en | May be HTML flipbook (`/HPA-2020-Annual-Report/`); PDF TBD |
| 2020 | financials | en | `.../2021/05/2020-Signed-FINAL-FS-HPA-2020.pdf` |

Search snippets also reference **2024/2025** annual + financials on the live page (post-dating the Dec 2024 Wayback snapshot). Confirm in-browser when acquiring.

### Older / additional (not blocking Phase 0)

- Stakeholder / annual-style: 2012–2019
- Financials: 2010–2019 (EN; some FR e.g. 2010, 2011)
- Sustainability, strategic plan, forced-labour supply-chain, AGM minutes → `report_type: other`

### Languages

- Primary corpus is **English**.
- French financials exist for some older years; recent bilingual annual coverage is unconfirmed — see `evals/README.md` for the bilingual eval gap note.

## Phase 0 exit / Phase 1a handoff

After PDFs are present in `manifest.yaml`, use these for the Phase 1a parse spike:

- Annual: `2023_annual_en.pdf`
- Financials: `2023_financials_en.pdf`
