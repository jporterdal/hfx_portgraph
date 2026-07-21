# Phase 1 parse quality gate

**Date:** 2026-07-21  
**Parser:** Docling (default)  
**Spike docs:** `2023_annual_en`, `2023_financials_en`

## Outcome: PASS (Docling retained)

Reviewed spike Markdown + `tables.md` sidecars. No Marker trial required.

### Table-heavy golden items checked (≥3)

| Golden id | Answerable from spike parse? | Evidence found |
|---|---|---|
| `gq-003` | Yes | 2023 financials income statement: fee/rental revenue, earnings from operations, net earnings $13,841 (2023) vs $13,815 (2022) |
| `gq-015` | Yes | Statement of financial position present in financials parse (cash/equivalents line available in tables) |
| `gq-019` / year columns | Yes | Comparative 2023/2022 columns preserved in financial statement tables |
| `gq-005` (throughput) | Yes | Annual report: containerized throughput **546,163 TEU** for 2023 with cargo stats sections |

### Notes

- Headings are present (H2-style) for chunking.
- Some OCR empty-page warnings appeared during Docling runs; body text and tables still extracted for these two PDFs.
- Literal phrase “operating income” is often “earnings from operations” / “net earnings” in these statements — golden `notes` should tolerate synonymy in later grading.
- **Later spike:** Marker on `2023_annual_en` pages 0–12 (`--mode fast --disable_ocr`) did not recover chart-borne KPIs into Markdown; it did export figure JPEGs. Follow-on path: design-heavy detect → Ollama VLM on crops (see `openspec/changes/phase-1-parse-rag/design.md` Decision 1b).
