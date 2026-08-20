"""Parent-child chunking over parsed Markdown."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hfx_portgraph.paths import chunks_path_for, parsed_dir_for

# ~4 chars/token heuristic when no tokenizer is available.
_CHARS_PER_TOKEN = 4
_MIN_CHILD_CHARS = 300 * _CHARS_PER_TOKEN
_MAX_CHILD_CHARS = 800 * _CHARS_PER_TOKEN
_TARGET_CHILD_CHARS = 500 * _CHARS_PER_TOKEN

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_PASSAGE_LABELS = ("text", "list_item")


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts


def _pack_children_detailed(paragraphs: list[str], max_chars: int = _MAX_CHILD_CHARS) -> list[dict]:
    """Pack paragraphs into children, keeping the source paragraph indices for each.

    Packing behavior is identical to the original text-only packer; this variant
    additionally reports which paragraph indices fed each child, so callers can
    resolve provenance without altering the packing algorithm itself.
    """
    children: list[dict] = []
    buf: list[str] = []
    buf_idx: list[int] = []
    size = 0

    def flush() -> None:
        if buf:
            children.append({"text": "\n\n".join(buf), "paragraph_indices": list(buf_idx)})

    for idx, para in enumerate(paragraphs):
        plen = len(para)
        if buf and size + plen + 2 > max_chars:
            flush()
            buf, buf_idx, size = [], [], 0
        if plen > max_chars:
            # Hard-split oversized paragraph.
            if buf:
                flush()
                buf, buf_idx, size = [], [], 0
            for i in range(0, plen, _TARGET_CHILD_CHARS):
                children.append({"text": para[i : i + _TARGET_CHILD_CHARS], "paragraph_indices": [idx]})
            continue
        buf.append(para)
        buf_idx.append(idx)
        size += plen + 2
        if size >= _MIN_CHILD_CHARS and size >= _TARGET_CHILD_CHARS:
            flush()
            buf, buf_idx, size = [], [], 0
    flush()
    return children


def _pack_children(paragraphs: list[str], max_chars: int = _MAX_CHILD_CHARS) -> list[str]:
    return [c["text"] for c in _pack_children_detailed(paragraphs, max_chars)]


def _parse_sections(markdown: str) -> list[dict]:
    """Split markdown into sections keyed by H2/H3 headings."""
    lines = markdown.splitlines()
    sections: list[dict] = []
    current = {
        "heading": "(preamble)",
        "level": 1,
        "lines": [],
    }

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current["lines"] or current["heading"] != "(preamble)":
                current["text"] = "\n".join(current["lines"]).strip()
                sections.append(current)
            level = len(m.group(1))
            current = {"heading": m.group(2).strip(), "level": level, "lines": []}
        else:
            current["lines"].append(line)

    current["text"] = "\n".join(current["lines"]).strip()
    sections.append(current)
    return [s for s in sections if s.get("text") or s["heading"] != "(preamble)"]


def _section_header_rows(provenance: list[dict]) -> list[tuple[int, dict]]:
    """(index, row) for every section_header-labeled provenance row, in document order."""
    return [(idx, row) for idx, row in enumerate(provenance) if row.get("label") == "section_header"]


def _passage_rows(provenance: list[dict], start: int, end: int) -> list[dict]:
    """Non-heading, non-picture provenance rows within provenance[start:end]."""
    return [row for row in provenance[start:end] if row.get("label") in _PASSAGE_LABELS]


def _page_range(pages: list[int]) -> tuple[int, int] | None:
    if not pages:
        return None
    return min(pages), max(pages)


def _resolve_section_pages(sections: list[dict], provenance: list[dict]) -> dict[int, dict]:
    """Positionally pair real (non-preamble) sections against section_header provenance rows.

    Pairing stops once one list runs out (divergence) rather than guessing; sections
    past that point are left unresolved. Returns, per resolved section index (into
    `sections`), its matched page range (if the row carried page data) plus the
    provenance-list slice bounds usable for scoping that section's passage rows.
    """
    header_rows = _section_header_rows(provenance)
    real_section_positions = [i for i, s in enumerate(sections) if s["heading"] != "(preamble)"]
    n_pairs = min(len(real_section_positions), len(header_rows))

    section_pages: dict[int, dict] = {}
    for k in range(n_pairs):
        sec_idx = real_section_positions[k]
        prov_idx, row = header_rows[k]
        prov_end = header_rows[k + 1][0] if k + 1 < len(header_rows) else len(provenance)
        entry = {"prov_start": prov_idx + 1, "prov_end": prov_end}
        page_range = _page_range(row.get("pages") or [])
        if page_range:
            entry["page_start"], entry["page_end"] = page_range
            entry["page_source"] = "matched"
        section_pages[sec_idx] = entry
    return section_pages


def chunk_report(report_id: str, *, force: bool = False) -> Path:
    parsed = parsed_dir_for(report_id)
    md_path = parsed / "document.md"
    meta_path = parsed / "meta.json"
    provenance_path = parsed / "provenance.json"
    if not md_path.exists():
        raise FileNotFoundError(f"missing parse output: {md_path}")

    out_path = chunks_path_for(report_id)
    if out_path.exists() and not force:
        return out_path

    markdown = md_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    year = meta.get("year")
    report_type = meta.get("report_type")
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else []
    )

    sections = _parse_sections(markdown)
    section_pages = _resolve_section_pages(sections, provenance)
    records: list[dict] = []
    child_n = 0

    for i, section in enumerate(sections):
        parent_id = f"{report_id}::parent::{i:04d}"
        heading = section["heading"]
        parent_text = section["text"]
        sec_page = section_pages.get(i, {})
        parent_page_start = sec_page.get("page_start")
        parent_page_end = sec_page.get("page_end")
        parent_page_source = sec_page.get("page_source")

        parent = {
            "chunk_id": parent_id,
            "role": "parent",
            "report_id": report_id,
            "year": year,
            "report_type": report_type,
            "heading": heading,
            "level": section["level"],
            "text": parent_text,
            "page_start": parent_page_start,
            "page_end": parent_page_end,
            "page_source": parent_page_source,
            "section": heading,
        }
        records.append(parent)

        passage_rows = (
            _passage_rows(provenance, sec_page["prov_start"], sec_page["prov_end"])
            if "prov_start" in sec_page
            else []
        )
        paragraphs = _split_paragraphs(parent_text)

        for child in _pack_children_detailed(paragraphs):
            child_n += 1
            child_pages: set[int] = set()
            for p_idx in child["paragraph_indices"]:
                if p_idx < len(passage_rows):
                    child_pages.update(passage_rows[p_idx].get("pages") or [])

            page_range = _page_range(list(child_pages))
            if page_range:
                child_page_start, child_page_end = page_range
                child_page_source = "matched"
            elif parent_page_start is not None:
                child_page_start, child_page_end = parent_page_start, parent_page_end
                child_page_source = "inherited"
            else:
                child_page_start = child_page_end = None
                child_page_source = None

            child_text = child["text"]
            records.append(
                {
                    "chunk_id": f"{report_id}::child::{child_n:05d}",
                    "role": "child",
                    "report_id": report_id,
                    "parent_id": parent_id,
                    "year": year,
                    "report_type": report_type,
                    "heading": heading,
                    "text": child_text,
                    "page_start": child_page_start,
                    "page_end": child_page_end,
                    "page_source": child_page_source,
                    "section": heading,
                    "approx_tokens": max(1, len(child_text) // _CHARS_PER_TOKEN),
                }
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


def load_chunks(report_id: str) -> list[dict]:
    path = chunks_path_for(report_id)
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_all_v1_chunks(report_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for rid in report_ids:
        rows.extend(load_chunks(rid))
    return rows
