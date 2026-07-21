"""Docling-based PDF parse into corpus/parsed/{report_id}/."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from hfx_portgraph.paths import parsed_dir_for, pdf_path_for, report_by_id


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
    markdown = _export_markdown(document)
    provenance = _collect_provenance(document)

    # Extract markdown tables into a sidecar for easier gate review.
    tables = re.findall(r"((?:\|.*\n)+)", markdown)
    tables_path = out_dir / "tables.md"
    if tables:
        tables_path.write_text("\n\n".join(t.strip() for t in tables), encoding="utf-8")
    elif tables_path.exists():
        tables_path.unlink()

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
