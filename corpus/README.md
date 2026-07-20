# Port of Halifax report corpus

Local inventory of public Port Authority reports used by `hfx_portgraph`.

**Source (live):** https://www.porthalifax.ca/about-us/port-authority/reports/  
**French UI path:** https://www.porthalifax.ca/a-propos-de-nous/administration-portuaire/rapports/?lang=fr  
**Inventory snapshot:** [Wayback Machine, 2024-12-14](https://web.archive.org/web/20241214192351/https://www.porthalifax.ca/about-us/port-authority/reports/)

> **Note (2026-07-20):** The live site and direct `wp-content` PDF URLs return Cloudflare challenges from automated clients. Prefer downloading in a normal browser, or use Wayback/original URLs from a machine that can pass CF. The fetch script will try live first, then Wayback.

## Layout

| Path | Purpose |
|---|---|
| `raw/` | Original PDF binaries (gitignored) |
| `manifest.yaml` | Metadata for each report (committed) |

## Filename convention

`{year}_{report_type}_{lang}.pdf`

- `report_type`: `annual` | `financials` | `other`
- `lang`: `en` | `fr` | `unknown`

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
| 2020 | annual | en | Linked from page (may be HTML flipbook `/HPA-2020-Annual-Report/`); PDF TBD |
| 2020 | financials | en | `.../2021/05/2020-Signed-FINAL-FS-HPA-2020.pdf` |

Search snippets also reference **2024/2025** annual + financials on the live page (post-dating the Dec 2024 Wayback snapshot). Confirm in-browser when acquiring.

### Older / additional (manifest as `other` or historical financials — not blocking Phase 0)

- Stakeholder / annual-style: 2012–2019 (various filenames)
- Financials: 2010–2019 (EN; some FR e.g. 2010, 2011)
- Sustainability, strategic plan, forced-labour supply-chain, AGM minutes → `report_type: other`

### Languages

- Page columns include **Language**; primary corpus is **English**.
- French financials exist for some older years; French reports page exists but bilingual coverage for recent annuals is **unconfirmed** until browser inventory. Treat as possible bilingual gap for eval tagging.

## Rebuild

_Download script and step-by-step manual fallback will be completed in tasks 2.2–2.6._
