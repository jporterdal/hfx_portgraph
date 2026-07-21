# Golden evaluation set

Phase 0 eval harness for Port of Halifax report questions. Used to baseline later RAG / LangGraph phases — **evidence shape over polished gold answers**.

## File

| Path | Purpose |
|---|---|
| `golden.jsonl` | One JSON object per line |
| `example_item.json` | Documented example of the required schema |

## Required fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable unique id |
| `question` | string | Natural-language question |
| `tags` | string[] | Controlled vocabulary only (see below) |
| `expected_evidence` | object | Must include `years` (array of ints). Should include `report_ids` and/or `filenames` matching `corpus/manifest.yaml`. Optional: `metrics`, `entities`, `page_hint` |
| `notes` | string | What correct grounding looks like |

## Controlled tags

`single_doc` · `yoy_metric` · `narrative` · `multi_hop` · `table_heavy` · `bilingual` · `year_collision`

## Gates (Phase 0 exit)

- Item count in **[20, 40]**
- **≥80%** of items have ≥1 controlled tag
- Hard cases: ≥1 `table_heavy`, ≥1 `year_collision`
- `bilingual`: include a tagged item **or** document a corpus gap below

## Bilingual coverage gap

As of Phase 0 inventory (Wayback Dec 2024 + catalog), **recent annual reports in the v1 English catalog do not have confirmed French PDF counterparts**. Older French financials exist on the site historically but are outside the v1 catalog. Therefore there is **no `bilingual` golden item** until a French PDF is present in `corpus/manifest.yaml` with `status: present`. Revisit after browser confirmation of the French reports page.

## Phase 0 exit / Phase 1a handoff

Year coverage target for v1 catalog: **2020–2023** annual + financials (2020 annual may remain missing if flipbook-only).

Recommended Phase 1a parse-spike PDFs (once downloaded):

- `2023_annual_en.pdf`
- `2023_financials_en.pdf`
