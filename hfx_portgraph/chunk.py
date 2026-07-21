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


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts


def _pack_children(paragraphs: list[str], max_chars: int = _MAX_CHILD_CHARS) -> list[str]:
    children: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        plen = len(para)
        if buf and size + plen + 2 > max_chars:
            children.append("\n\n".join(buf))
            buf = []
            size = 0
        if plen > max_chars:
            # Hard-split oversized paragraph.
            if buf:
                children.append("\n\n".join(buf))
                buf, size = [], 0
            for i in range(0, plen, _TARGET_CHILD_CHARS):
                children.append(para[i : i + _TARGET_CHILD_CHARS])
            continue
        buf.append(para)
        size += plen + 2
        if size >= _MIN_CHILD_CHARS and size >= _TARGET_CHILD_CHARS:
            children.append("\n\n".join(buf))
            buf, size = [], 0
    if buf:
        children.append("\n\n".join(buf))
    return children


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


def chunk_report(report_id: str, *, force: bool = False) -> Path:
    parsed = parsed_dir_for(report_id)
    md_path = parsed / "document.md"
    meta_path = parsed / "meta.json"
    if not md_path.exists():
        raise FileNotFoundError(f"missing parse output: {md_path}")

    out_path = chunks_path_for(report_id)
    if out_path.exists() and not force:
        return out_path

    markdown = md_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    year = meta.get("year")
    report_type = meta.get("report_type")

    sections = _parse_sections(markdown)
    records: list[dict] = []
    child_n = 0

    for i, section in enumerate(sections):
        parent_id = f"{report_id}::parent::{i:04d}"
        heading = section["heading"]
        parent_text = section["text"]
        parent = {
            "chunk_id": parent_id,
            "role": "parent",
            "report_id": report_id,
            "year": year,
            "report_type": report_type,
            "heading": heading,
            "level": section["level"],
            "text": parent_text,
            "page_start": None,
            "page_end": None,
            "section": heading,
        }
        records.append(parent)

        for j, child_text in enumerate(_pack_children(_split_paragraphs(parent_text))):
            child_n += 1
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
                    "page_start": None,
                    "page_end": None,
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
