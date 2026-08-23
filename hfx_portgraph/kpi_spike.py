"""Spike: detect design-heavy pages, source figure crops, extract KPI facts via a local VLM.

Post-pass over already-parsed Docling artifacts (`corpus/parsed/{report_id}/`) — does not touch
the Phase 1 parse path. See `openspec/changes/visual-kpi-vlm-extraction/design.md`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from hfx_portgraph.paths import CORPUS_DIR, PARSED_DIR, RAW_DIR, report_by_id

KPI_FACTS_DIR = CORPUS_DIR / "kpi_facts"

# Section-heading phrases that mark the infographic/dashboard pages Halifax annual reports use.
DASHBOARD_KEYWORDS = [
    "at-a-glance",
    "sources of revenue",
    "cargo stats",
    "financial health",
    "cruise season",
]

# Fallback signal for pages with no dashboard heading but a heavy figure/text imbalance.
MIN_DENSITY_PICTURES = 3
MAX_DENSITY_WORDS = 40

# A crop "looks like a chart" (flat vector graphic, not a photo) if it is big enough to hold
# labeled data and its pixels are either mostly near-white OR dominated by a handful of flat
# colors. Calibrated against 2023_annual_en pages 5-7: white-background bar/pie charts scored
# white_frac 0.39-0.93; a green-background map chart scored white_frac 0.04 but dominant_frac
# 0.54; ship/container photos scored <0.04 white_frac and <0.38 dominant_frac either way.
# Decorative icons were excluded by the area floor regardless of color signal.
MIN_CHART_AREA = 20_000
CHART_WHITE_FRAC = 0.30
CHART_DOMINANT_COLOR_FRAC = 0.50

VLM_MODEL = os.environ.get("HFX_VLM_MODEL", "qwen2.5vl:7b")


# ---------------------------------------------------------------------------
# 1. Design-heavy page detection
# ---------------------------------------------------------------------------


@dataclass
class PageProfile:
    page: int
    headings: list[str] = field(default_factory=list)
    picture_count: int = 0
    word_count: int = 0


@dataclass
class DesignHeavyPage:
    page: int
    headings: list[str]
    picture_count: int
    word_count: int
    reason: str


def load_provenance(report_id: str) -> list[dict]:
    path = PARSED_DIR / report_id / "provenance.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _page_profiles(provenance: list[dict]) -> dict[int, PageProfile]:
    profiles: dict[int, PageProfile] = {}
    for row in provenance:
        label = row.get("label")
        text = (row.get("text_preview") or "").strip()
        for page in row.get("pages") or []:
            prof = profiles.setdefault(page, PageProfile(page=page))
            if label == "picture":
                prof.picture_count += 1
            elif label == "section_header":
                if text:
                    prof.headings.append(text)
            elif label in ("text", "list_item"):
                prof.word_count += len(text.split())
    return profiles


# Real section titles in this corpus are short ("2023 SOURCES OF REVENUE" = 24 chars); longer
# strings are usually body text Docling mislabeled as a heading (e.g. a cross-reference sentence
# that happens to contain "Cargo Stats"), so they don't count as a dashboard-heading match.
MAX_HEADING_LEN = 40


def _dashboard_keyword_match(headings: list[str]) -> str | None:
    for heading in headings:
        if len(heading) > MAX_HEADING_LEN:
            continue
        low = heading.lower()
        for keyword in DASHBOARD_KEYWORDS:
            if keyword in low:
                return keyword
    return None


def detect_design_heavy_pages(report_id: str) -> list[DesignHeavyPage]:
    """Flag pages likely to have chart-borne KPIs Docling lost to `<!-- image -->` stubs.

    A page is flagged if either:
    - one of its headings matches a known dashboard-style phrase (and it has >=1 picture), or
    - it has a high picture:text imbalance (>=3 pictures, <=40 words of body text) with no
      recognized heading — catches sub-pages of a dashboard section that inherit no heading of
      their own (e.g. a cargo-stats page continued from the prior page).
    """
    profiles = _page_profiles(load_provenance(report_id))
    flagged: list[DesignHeavyPage] = []
    for page in sorted(profiles):
        prof = profiles[page]
        keyword = _dashboard_keyword_match(prof.headings)
        if keyword and prof.picture_count >= 1:
            reason = f"heading matches dashboard pattern {keyword!r}"
        elif prof.picture_count >= MIN_DENSITY_PICTURES and prof.word_count <= MAX_DENSITY_WORDS:
            reason = (
                f"high figure density ({prof.picture_count} pictures, "
                f"{prof.word_count} body words)"
            )
        else:
            continue
        flagged.append(
            DesignHeavyPage(
                page=page,
                headings=prof.headings,
                picture_count=prof.picture_count,
                word_count=prof.word_count,
                reason=reason,
            )
        )
    return flagged


def page_context_text(report_id: str, page: int) -> str:
    """Best-effort heading + body text for a page, to help the VLM label chart values."""
    prof = _page_profiles(load_provenance(report_id)).get(page)
    if not prof:
        return ""
    lines = list(prof.headings)
    for row in load_provenance(report_id):
        if page in (row.get("pages") or []) and row.get("label") in ("text", "list_item"):
            text = (row.get("text_preview") or "").strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Figure-crop sourcing (Docling image export -> Marker crop -> full-page render)
# ---------------------------------------------------------------------------


@dataclass
class FigureCrop:
    report_id: str
    page: int
    source: str  # "docling" | "marker" | "render"
    path: Path
    figure_id: str


def _white_fraction(path: Path) -> float:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w * h > 4_000_000:
        img = img.resize((w // 4, h // 4))
    pixels = list(img.getdata())
    white = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235)
    return white / len(pixels) if pixels else 0.0


def _dominant_color_fraction(path: Path, *, top_n: int = 6) -> float:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w * h > 4_000_000:
        img = img.resize((w // 4, h // 4))
    quantized = img.quantize(colors=32, method=Image.MEDIANCUT).convert("RGB")
    counts = quantized.getcolors(maxcolors=1_000_000) or []
    if not counts:
        return 0.0
    counts.sort(reverse=True)
    total = sum(c for c, _ in counts)
    top = sum(c for c, _ in counts[:top_n])
    return top / total if total else 0.0


def _area(path: Path) -> int:
    from PIL import Image

    with Image.open(path) as img:
        return img.width * img.height


def _is_chart_like(path: Path) -> bool:
    if _area(path) < MIN_CHART_AREA:
        return False
    return (
        _white_fraction(path) >= CHART_WHITE_FRAC
        or _dominant_color_fraction(path) >= CHART_DOMINANT_COLOR_FRAC
    )


def docling_picture_crops(report_id: str, *, force: bool = False) -> dict[int, list[Path]]:
    """Convert the source PDF with picture-image export enabled; cache crops + a manifest to disk.

    Returns {page: [crop paths]}. Docling assigns pictures to the page(s) named in their
    provenance, independent of the (imageless) `corpus/parsed/` markdown artifact.
    """
    out_dir = KPI_FACTS_DIR / report_id / "crops" / "docling"
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists() and not force:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {int(page): [Path(p) for p in paths] for page, paths in raw.items()}

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    report = report_by_id(report_id)
    pdf_path = RAW_DIR / report["filename"]

    opts = PdfPipelineOptions()
    opts.generate_picture_images = True
    opts.images_scale = 2.0
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    result = converter.convert(str(pdf_path))
    document = result.document

    out_dir.mkdir(parents=True, exist_ok=True)
    by_page: dict[int, list[Path]] = {}
    for i, picture in enumerate(document.pictures):
        pages = sorted({p.page_no for p in (picture.prov or []) if p.page_no is not None})
        if not pages:
            continue
        image = picture.get_image(document)
        if image is None:
            continue
        page = pages[0]
        crop_path = out_dir / f"page{page}_pic{i}.png"
        image.save(crop_path)
        by_page.setdefault(page, []).append(crop_path)

    manifest_path.write_text(
        json.dumps({str(p): [str(cp) for cp in cps] for p, cps in by_page.items()}, indent=2),
        encoding="utf-8",
    )
    return by_page


def marker_crop_paths(report_id: str, docling_page: int) -> list[Path]:
    """Marker spike crops (if present) live under `corpus/parsed/{report_id}_marker_spike/`.

    Marker's page numbering is 0-indexed; Docling's (and this module's) is 1-indexed, confirmed
    against `_page_4_Figure_9.jpeg` = the docling-page-5 Sources of Revenue chart.
    """
    marker_dir = PARSED_DIR / f"{report_id}_marker_spike" / report_id
    if not marker_dir.exists():
        return []
    marker_page_id = docling_page - 1
    return sorted(marker_dir.glob(f"_page_{marker_page_id}_*.jp*g"))


def render_full_page(report_id: str, page: int, *, force: bool = False) -> Path:
    """Last-resort crop source: render the whole PDF page (loses precision, gains coverage)."""
    out_dir = KPI_FACTS_DIR / report_id / "crops" / "render"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page{page}.png"
    if out_path.exists() and not force:
        return out_path

    import pypdfium2 as pdfium

    report = report_by_id(report_id)
    pdf = pdfium.PdfDocument(str(RAW_DIR / report["filename"]))
    bitmap = pdf[page - 1].render(scale=2.0)
    bitmap.to_pil().save(out_path)
    return out_path


def source_crop_for_page(report_id: str, page: int) -> FigureCrop:
    """Pick a crop for a flagged page: Docling chart-like crop, else Marker, else full-page render."""
    docling_candidates = docling_picture_crops(report_id).get(page, [])
    chart_like = [p for p in docling_candidates if _is_chart_like(p)]
    if chart_like:
        best = max(chart_like, key=_area)
        return FigureCrop(report_id, page, "docling", best, figure_id=best.stem)

    marker_candidates = marker_crop_paths(report_id, page)
    marker_chart_like = [p for p in marker_candidates if _is_chart_like(p)]
    if marker_chart_like:
        best = max(marker_chart_like, key=_area)
        return FigureCrop(report_id, page, "marker", best, figure_id=best.stem)

    render_path = render_full_page(report_id, page)
    return FigureCrop(report_id, page, "render", render_path, figure_id=render_path.stem)


# ---------------------------------------------------------------------------
# 3. Local Ollama VLM extraction
# ---------------------------------------------------------------------------

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_json_array(content: str) -> list[dict]:
    match = _JSON_ARRAY_RE.search(content)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def extract_facts_from_crop(crop: FigureCrop, *, year: int) -> list[dict]:
    """Run the local vision model against one crop; return kpi_facts-shaped dicts."""
    import ollama

    context = page_context_text(crop.report_id, crop.page)
    prompt = (
        "This image is a chart or infographic from an annual report. "
        "Every numeric `value` and `unit` you output MUST be read directly off the chart in the "
        "image, never computed or copied from the text below — that text describes other numbers "
        "on the same page that are unrelated to this specific chart. "
        "If a slice/bar in the chart has no text label of its own printed in the image, you MUST "
        "still write a descriptive `label` by matching its value against numbers in the "
        "surrounding page text below (e.g. if the chart shows an unlabeled '91%' slice and the "
        "text separately gives a breakdown like 'Category A: 4,209,781' and 'Category B: 403,642' "
        "totaling close to the chart's whole, and 4,209,781 is ~91% of that total, then label the "
        "91% slice 'Category A'). Never let the text change the `value` shown in the chart itself, "
        "only the wording of the `label`.\n\n"
        f"Surrounding page text:\n{context}\n\n"
        "Extract each labeled data point actually drawn in the chart image as a JSON array of "
        "objects with fields label (string), value (number, as shown in the chart), unit (string, "
        "e.g. '%', 'MT', 'TEU', matching what the chart displays). "
        "Return ONLY the JSON array, no prose, no markdown fences."
    )
    try:
        resp = ollama.chat(
            model=VLM_MODEL,
            messages=[{"role": "user", "content": prompt, "images": [str(crop.path)]}],
            options={"temperature": 0},
        )
    except ConnectionError as exc:
        raise SystemExit(
            "Cannot reach Ollama for VLM extraction. Install/start it, then:\n"
            f"  ollama pull {VLM_MODEL}\n"
            "See docs/phase-1.md"
        ) from exc

    content = resp["message"]["content"] if isinstance(resp, dict) else resp.message.content
    raw_facts = _parse_json_array(content)

    facts = []
    for item in raw_facts:
        if not isinstance(item, dict) or "label" not in item or "value" not in item:
            continue
        facts.append(
            {
                "label": item.get("label"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "year": year,
                "report_id": crop.report_id,
                "page": crop.page,
                "figure_id": crop.figure_id,
            }
        )
    return facts


def write_kpi_facts(report_id: str, facts: list[dict]) -> Path:
    out_path = KPI_FACTS_DIR / f"{report_id}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in facts:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


def run_spike(report_id: str, *, pages: list[int] | None = None) -> Path:
    """Full pipeline: detect -> source crops -> extract -> write sidecar."""
    report = report_by_id(report_id)
    year = report.get("year")

    flagged = detect_design_heavy_pages(report_id)
    if pages:
        flagged = [p for p in flagged if p.page in pages]

    all_facts: list[dict] = []
    for page_info in flagged:
        crop = source_crop_for_page(report_id, page_info.page)
        facts = extract_facts_from_crop(crop, year=year)
        all_facts.extend(facts)

    return write_kpi_facts(report_id, all_facts)
