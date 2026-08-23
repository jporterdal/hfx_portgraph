# Visual KPI VLM extraction spike

**Date:** 2026-08-22
**Change:** `openspec/changes/visual-kpi-vlm-extraction/`
**Report:** `2023_annual_en` only (spike scope)

## Outcome: PASS

Both required scenarios produced correct, citable facts:

- Sources of Revenue (page 5): 41% Cargo / 35% Real Estate / 12% Cruise / 9% Pyritic Slate
  Sequestration / 3% Other — matches the Marker-spike ground truth exactly.
- Cargo Stats (page 6): 91% HPA Containerized Cargo / 9% HPA Non-Containerized Cargo — matches
  `4,209,781 / 4,613,423 MT` already recovered as text.

Two bonus pages (4, 7) also flagged and extracted; see notes below on their reliability.

Full decision writeup: `openspec/changes/visual-kpi-vlm-extraction/design.md` ("Spike Results" and
"Decision 6").

## Command sequence

```bash
ollama serve                        # if not already running
ollama pull qwen2.5vl:7b            # vision-capable local model, ~6GB

.venv/bin/python scripts/spike_kpi_detect.py --report-id 2023_annual_en
.venv/bin/python scripts/spike_kpi_crops.py  --report-id 2023_annual_en
.venv/bin/python scripts/spike_kpi_extract.py --report-id 2023_annual_en

cat corpus/kpi_facts/2023_annual_en.jsonl
```

`scripts/spike_kpi_extract.py` runs the full detect → source-crop → VLM-extract → write pipeline
in one step; the detect/crops scripts exist standalone for inspecting intermediate output.

## Detection

Flagged pages 4 ("2023 AT-A-GLANCE"), 5 ("2023 SOURCES OF REVENUE"), 6 ("2023 CARGO STATS"), and 7
(figure-density fallback, no heading of its own — a map chart continuing the Cargo Stats section).
No false positives on financial-statement (pages 11-13) or narrative pages. See design.md Decision
2 for the heuristic and its calibration against false positives found along the way (a Strategic
Vision page with decorative icons, a cross-reference sentence containing "Cargo Stats").

## Crop sourcing

Docling image export (`generate_picture_images=True`, `images_scale=2.0`) produced usable,
precise crops for pages 5, 6, and 7 — as good as or better than the earlier Marker-spike crops, so
Marker fell back to unused for this report. Page 4's only pictures were decorative icons/photos
below the chart-like size/color threshold, so it fell through to a full-page `pypdfium2` render.

A "flat-graphic" filter (area >= 20,000px² AND (near-white pixel fraction >= 30% OR top-6
quantized colors cover >= 50% of pixels)) separated real charts from decorative icons and photos.
The two-condition OR was needed after the white-fraction-only version missed a green-background
world map chart on page 7 (white_frac 0.04, but only six flat colors covering the map) — caught by
inspecting the actual crop, not by the heuristic itself.

## VLM extraction

Model: `qwen2.5vl:7b` via local Ollama (chosen over `llava`/`moondream` for chart/infographic
reading strength; no cloud calls). Two prompt/pipeline bugs were found and fixed mid-spike:

1. **Bad crop, ungrounded answer:** when no chart-like crop existed anywhere (page 4), the
   original fallback chain accepted a non-chart Marker photo (a container ship, no numbers) rather
   than falling through further. The VLM didn't refuse — it silently answered from unrelated page
   text, producing plausible but ungrounded facts with wrong labels. Fixed by only accepting a
   Marker candidate that itself passes the chart-like filter, otherwise rendering the full page
   (which legitimately contains the same printed numbers as real pixels).
2. **Text context overriding chart values:** the first extraction prompt let page body text
   override what the image showed — the model reported tonnage figures from nearby text instead
   of the pie chart's own 91%/9%. Fixed by instructing the model that `value`/`unit` must come
   only from the image; page text may only be used to word a `label` for chart elements with no
   text of their own (needed for both target pie/bar charts, which label their own slices, and the
   page-7/page-4 cases, which don't).

## Known limitations (not required to close this spike)

- The chart-like crop filter is a spike-grade heuristic (pixel color statistics, not real vision),
  calibrated on ~15 examples from one report. It will misclassify some crops on other reports.
- Labels the VLM invents for chart elements with no on-image text (e.g. matching an unlabeled pie
  slice to a category named only in nearby body text) are a plausibility judgment, not a
  guaranteed-correct one — spot-checked qualitatively here, not scored.
- Corpus-wide accuracy (beyond `2023_annual_en`) is unproven — explicitly out of scope per this
  change's Non-Goals.
