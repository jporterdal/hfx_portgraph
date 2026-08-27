"""Docling-based PDF parse into corpus/parsed/{report_id}/."""

from __future__ import annotations

import difflib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from hfx_portgraph.paths import parsed_dir_for, pdf_path_for, report_by_id

# --- Fused furniture-detection signal: named, documented constants ---
# See openspec/changes/strip-page-furniture/design.md Decision 1 for the empirical
# basis of each value. All thresholds are relative (fractions of page/document size),
# not fixed pixel or count values, so they don't overfit to one report's layout.

TWO_UP_ASPECT_RATIO_THRESHOLD = 1.4
"""Page width/height ratio above which a page is treated as a 2-up spread (two
independently-laid-out printed pages side by side) rather than a single page.
Basis: 2020_annual_en's 2-up pages measure 1440x720pt (ratio 2.0); its single-page
cover/back-cover measure 720x720 (ratio 1.0). Typical single portrait or landscape
report pages sit at or below ~1.3."""

TEXT_SIMILARITY_THRESHOLD = 0.82
"""difflib.SequenceMatcher ratio, on digit-normalized text, above which two items'
text is considered a repeat of each other. Tolerant of OCR/extraction corruption
(2021_annual_en's cipher-garbled footer text) rather than requiring an exact match."""

TEXT_LENGTH_RATIO_THRESHOLD = 0.90
"""min(len(a), len(b)) / max(len(a), len(b)) gate applied alongside the ratio
above. Needed because SequenceMatcher's character-overlap ratio alone rates a
short string highly similar to a longer string that merely contains it as a
substring (e.g. "Property and equipment" vs "7. Property and equipment" scores
0.936 -- above threshold -- despite being two distinct document elements, a
false positive found in 2020_annual_en). The known true-positive OCR-corrupted
case (2021_annual_en's page-14 footer glitch) has a length ratio of 0.95, well
clear of this gate; the false-positive pair above sits at 0.88, below it."""

POSITION_VARIANCE_FRAC = 0.02
"""Max allowed population stdev of top_frac within a position cluster, as a
fraction of page height, for that cluster's position to count as "consistent".
Basis: design.md measured known furniture at 0.0-0.6% variance across occurrences,
versus 60+ points of page-height scatter for one-off real headings -- 2% sits
comfortably above furniture noise and far below real-heading scatter."""

Y_BAND_FRAC = 0.03
"""Bucket width (fraction of page height) used to group items into candidate
position bands before scoring within-band variance."""

MIN_OCCURRENCE_FLOOR = 3
MIN_OCCURRENCE_FRACTION = 0.02
"""An item's text/position must recur at least
max(MIN_OCCURRENCE_FLOOR, ceil(MIN_OCCURRENCE_FRACTION * total_pages)) times
(on distinct pages) to count as corroborating "repeat" evidence -- expressed
relative to document length, not a fixed integer, per design.md's overfitting
guardrails."""

POSITION_CANDIDATE_MAX_CHARS = 300
"""Items longer than this (normalized text) are never considered furniture
candidates for the text-repeat/position signals -- real page furniture (running
headers/footers, letterhead, address blocks) is always short chrome, not a body
paragraph, so scoping to short items keeps the O(n^2) similarity clustering cheap
and avoids matching long, legitimately-repeated boilerplate paragraphs."""

_DIGIT_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Digit-normalize and collapse whitespace for fuzzy repeat matching."""
    t = (text or "").strip().lower()
    t = _DIGIT_RE.sub("#", t)
    t = _WS_RE.sub(" ", t)
    return t


def text_similarity(a: str, b: str) -> float:
    """Character-level similarity ratio, tolerant of OCR/extraction corruption."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_text_repeat_match(a: str, b: str) -> bool:
    """True if `a` and `b` should be treated as the same repeated text.

    Requires both a high character-similarity ratio and comparable length
    (see TEXT_LENGTH_RATIO_THRESHOLD) so a short string that merely appears as
    a substring of a longer, distinct one isn't misclassified as a repeat.
    """
    if not a or not b:
        return False
    length_ratio = min(len(a), len(b)) / max(len(a), len(b))
    if length_ratio < TEXT_LENGTH_RATIO_THRESHOLD:
        return False
    return text_similarity(a, b) >= TEXT_SIMILARITY_THRESHOLD


def cluster_by_text_similarity(normalized_texts: list[str]) -> list[list[int]]:
    """Group indices of `normalized_texts` by fuzzy similarity, with counts.

    Returns a list of clusters (each a list of indices into `normalized_texts`),
    including singleton clusters for items with no match.
    """
    n = len(normalized_texts)
    assigned = [-1] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if assigned[i] != -1 or not normalized_texts[i]:
            continue
        cluster = [i]
        assigned[i] = len(clusters)
        for j in range(i + 1, n):
            if assigned[j] != -1 or not normalized_texts[j]:
                continue
            if is_text_repeat_match(normalized_texts[i], normalized_texts[j]):
                cluster.append(j)
                assigned[j] = len(clusters)
        clusters.append(cluster)
    return clusters


def _min_occurrence_threshold(total_pages: int) -> int:
    return max(MIN_OCCURRENCE_FLOOR, math.ceil(MIN_OCCURRENCE_FRACTION * max(total_pages, 1)))


def _page_aspect_is_two_up(width: float, height: float) -> bool:
    if not width or not height:
        return False
    return (width / height) >= TWO_UP_ASPECT_RATIO_THRESHOLD


def _collect_items(document) -> list[dict]:
    """Capture every item (including FURNITURE-layer) with normalized bbox position.

    One record per (item, page) occurrence -- an item spanning multiple pages
    yields multiple records, which is what occurrence counting needs.
    """
    from docling_core.types.doc.document import ContentLayer

    pages = document.pages or {}
    items: list[dict] = []
    order = 0
    for item, _level in document.iterate_items(included_content_layers=set(ContentLayer)):
        text = (getattr(item, "text", None) or "").strip()
        label = getattr(item, "label", None)
        label_s = getattr(label, "value", str(label) if label is not None else "")
        content_layer = getattr(item, "content_layer", None)
        content_layer_s = getattr(
            content_layer, "value", str(content_layer) if content_layer is not None else ""
        )
        prov_list = getattr(item, "prov", None) or []
        if not prov_list:
            continue
        for prov in prov_list:
            page_no = getattr(prov, "page_no", None)
            bbox = getattr(prov, "bbox", None)
            top_frac = bottom_frac = left_frac = right_frac = None
            x_band = 0
            two_up = False
            page = pages.get(page_no) if page_no is not None else None
            size = getattr(page, "size", None) if page is not None else None
            if bbox is not None and size and size.width and size.height:
                two_up = _page_aspect_is_two_up(size.width, size.height)
                tl_bbox = bbox.to_top_left_origin(size.height)
                top_frac = tl_bbox.t / size.height
                bottom_frac = tl_bbox.b / size.height
                left_frac = tl_bbox.l / size.width
                right_frac = tl_bbox.r / size.width
                if two_up:
                    center_x = (left_frac + right_frac) / 2
                    x_band = 0 if center_x < 0.5 else 1
            items.append(
                {
                    "order": order,
                    "text": text,
                    "normalized_text": normalize_text(text),
                    "label": label_s,
                    "content_layer": content_layer_s,
                    "page_no": int(page_no) if page_no is not None else None,
                    "top_frac": top_frac,
                    "bottom_frac": bottom_frac,
                    "left_frac": left_frac,
                    "right_frac": right_frac,
                    "x_band": x_band,
                    "two_up_page": two_up,
                    "node_item": item,
                }
            )
            order += 1
    return items


def _position_consistency(
    items: list[dict], candidate_idx: list[int], min_occurrences: int
) -> dict[int, dict]:
    """Bucket candidate items by (y-band, x-band) and score position variance."""
    buckets: dict[tuple[int, int], list[int]] = {}
    for i in candidate_idx:
        top_frac = items[i]["top_frac"]
        if top_frac is None:
            continue
        y_key = round(top_frac / Y_BAND_FRAC)
        x_key = items[i]["x_band"]
        buckets.setdefault((y_key, x_key), []).append(i)

    result: dict[int, dict] = {}
    for idxs in buckets.values():
        if len(idxs) < 2:
            continue
        top_fracs = [items[i]["top_frac"] for i in idxs]
        variance = statistics.pstdev(top_fracs)
        pages = {items[i]["page_no"] for i in idxs}
        occurrence_count = len(pages)
        consistent = variance <= POSITION_VARIANCE_FRAC and occurrence_count >= min_occurrences
        for i in idxs:
            result[i] = {"variance": variance, "occurrence_count": occurrence_count, "consistent": consistent}
    return result


def classify_item(docling_flag: bool, text_repeat: bool, position_consistent: bool) -> tuple[bool, list[str]]:
    """Pure 2-of-3 fusion decision. Returns (is_furniture, signals_fired).

    Docling+text-repeat is definitive (fast-track); text-repeat+position is
    furniture; Docling+position (text singleton) is furniture; any single
    signal alone is NOT furniture. All of these are exactly "at least 2 of 3".
    """
    signals = []
    if docling_flag:
        signals.append("docling")
    if text_repeat:
        signals.append("text_repeat")
    if position_consistent:
        signals.append("position")
    return len(signals) >= 2, signals


def classify_furniture(items: list[dict], total_pages: int) -> list[dict]:
    """Run the fused furniture-detection signal over every captured item.

    Returns one classification record per item (same order as `items`, minus
    the raw `node_item` reference), each carrying its signals and decision.
    """
    min_occurrences = _min_occurrence_threshold(total_pages)

    candidate_idx = [
        i
        for i, it in enumerate(items)
        if it["normalized_text"] and len(it["normalized_text"]) <= POSITION_CANDIDATE_MAX_CHARS
    ]

    candidate_texts = [items[i]["normalized_text"] for i in candidate_idx]
    text_clusters = cluster_by_text_similarity(candidate_texts)
    text_repeat_count: dict[int, int] = {}
    for cluster in text_clusters:
        global_idxs = [candidate_idx[c] for c in cluster]
        pages_in_cluster = {items[g]["page_no"] for g in global_idxs}
        count = len(pages_in_cluster)
        for g in global_idxs:
            text_repeat_count[g] = count

    position_info = _position_consistency(items, candidate_idx, min_occurrences)

    results: list[dict] = []
    for i, it in enumerate(items):
        docling_flag = it["content_layer"] == "furniture"
        repeat_count = text_repeat_count.get(i, 1)
        text_repeat = repeat_count >= min_occurrences
        pos = position_info.get(i)
        position_consistent = bool(pos and pos["consistent"])
        is_furniture, signals = classify_item(docling_flag, text_repeat, position_consistent)
        results.append(
            {
                "order": it["order"],
                "text": it["text"],
                "normalized_text": it["normalized_text"],
                "label": it["label"],
                "content_layer": it["content_layer"],
                "page_no": it["page_no"],
                "top_frac": it["top_frac"],
                "bottom_frac": it["bottom_frac"],
                "left_frac": it["left_frac"],
                "right_frac": it["right_frac"],
                "x_band": it["x_band"],
                "two_up_page": it["two_up_page"],
                "docling_flag": docling_flag,
                "text_repeat_count": repeat_count,
                "text_repeat_signal": text_repeat,
                "position_signal": position_consistent,
                "position_variance": pos["variance"] if pos else None,
                "signals_fired": signals,
                "classification": "furniture" if is_furniture else "kept",
            }
        )
    return results


def _export_markdown(document) -> str:
    return document.export_to_markdown()


def _collect_provenance(document) -> list[dict]:
    """Best-effort page/heading provenance from Docling document items."""
    rows: list[dict] = []
    try:
        iterator = document.iterate_items()
    except Exception:
        return rows

    for item, level in iterator:
        text = getattr(item, "text", None) or ""
        label = getattr(item, "label", None)
        label_s = str(label) if label is not None else ""
        pages: list[int] = []
        prov = getattr(item, "prov", None) or []
        for p in prov:
            page_no = getattr(p, "page_no", None)
            if page_no is not None:
                try:
                    pages.append(int(page_no))
                except (TypeError, ValueError):
                    pass
        if not text and not pages:
            continue
        rows.append(
            {
                "level": level,
                "label": label_s,
                "text_preview": (text or "")[:240],
                "pages": sorted(set(pages)),
            }
        )
    return rows


def parse_report(report_id: str, *, force: bool = False) -> Path:
    """Parse one manifest report id. Returns parsed directory path."""
    from docling.document_converter import DocumentConverter

    report = report_by_id(report_id)
    if report.get("status") != "present":
        raise ValueError(f"{report_id} is not status=present in manifest")

    out_dir = parsed_dir_for(report_id)
    md_path = out_dir / "document.md"
    meta_path = out_dir / "meta.json"

    if md_path.exists() and meta_path.exists() and not force:
        return out_dir

    pdf = pdf_path_for(report)
    out_dir.mkdir(parents=True, exist_ok=True)

    converter = DocumentConverter()
    result = converter.convert(str(pdf))
    document = result.document

    items = _collect_items(document)
    total_pages = len(document.pages or {}) or max(
        (it["page_no"] for it in items if it["page_no"] is not None), default=0
    )
    classified = classify_furniture(items, total_pages)

    furniture_nodes = []
    seen_ids: set[int] = set()
    for it, cls in zip(items, classified):
        if cls["classification"] == "furniture":
            node = it["node_item"]
            if id(node) not in seen_ids:
                seen_ids.add(id(node))
                furniture_nodes.append(node)

    if furniture_nodes:
        document.delete_items(node_items=furniture_nodes)

    markdown = _export_markdown(document)
    provenance = _collect_provenance(document)

    # Extract markdown tables into a sidecar for easier gate review.
    tables = re.findall(r"((?:\|.*\n)+)", markdown)
    tables_path = out_dir / "tables.md"
    if tables:
        tables_path.write_text("\n\n".join(t.strip() for t in tables), encoding="utf-8")
    elif tables_path.exists():
        tables_path.unlink()

    items_path = out_dir / "items.jsonl"
    with items_path.open("w", encoding="utf-8") as f:
        for cls in classified:
            f.write(json.dumps(cls, ensure_ascii=False) + "\n")

    md_path.write_text(markdown, encoding="utf-8")
    meta = {
        "report_id": report_id,
        "source_pdf": report.get("filename"),
        "filename": report.get("filename"),
        "year": report.get("year"),
        "report_type": report.get("report_type"),
        "parser": "docling",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "markdown_chars": len(markdown),
        "provenance_item_count": len(provenance),
        "provenance_sample": provenance[:50],
        "has_tables_sidecar": bool(tables),
        "items_considered": len(classified),
        "items_stripped_as_furniture": len(furniture_nodes),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir


def heading_page_map(markdown: str, provenance: list[dict]) -> dict[str, list[int]]:
    """Map heading text → pages using provenance previews (best effort)."""
    mapping: dict[str, list[int]] = {}
    for row in provenance:
        preview = (row.get("text_preview") or "").strip()
        pages = row.get("pages") or []
        if preview and pages:
            mapping[preview] = pages
    # Also index markdown headings for chunker fallback.
    for line in markdown.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            mapping.setdefault(title, [])
    return mapping
