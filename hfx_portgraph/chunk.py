"""Parent-child chunking over parsed Markdown."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hfx_portgraph.parse import is_text_repeat_match, normalize_text
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


def _split_heading_stream(markdown: str) -> list[dict]:
    """First pass: split markdown into raw sections keyed by H2/H3 headings,
    with no running-header folding applied yet."""
    lines = markdown.splitlines()
    sections: list[dict] = []
    current = {"heading": "(preamble)", "level": 1, "lines": []}

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current["lines"] or current["heading"] != "(preamble)":
                sections.append(current)
            level = len(m.group(1))
            current = {"heading": m.group(2).strip(), "level": level, "lines": []}
        else:
            current["lines"].append(line)

    sections.append(current)
    return sections


_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+)[.\)]\s+")


def _leading_number(heading: str) -> str | None:
    m = _LEADING_NUMBER_RE.match(heading)
    return m.group(1) if m else None


def _headings_match(a: str, b: str) -> bool:
    """Fuzzy-match two raw heading strings for the running-header registry.

    A heading's leading number label (e.g. "7." in "7. Property and
    equipment") is load-bearing identity, not noise: two headings are only
    compared by fuzzy text similarity when they agree on having (or lacking)
    the same leading number. Without this guard, a bare similarity ratio
    wrongly merges same-words-different-note collisions found in
    2020_annual_en -- "Property and equipment" (a distinct heading) vs
    "7. Property and equipment" (Note 7's real heading), and "Property and
    equipment (continued)" vs "7. Property and equipment (continued)" -- both
    score above a reasonable similarity threshold on text alone, since a
    short numeric prefix is a small fraction of a longer shared string.
    """
    if _leading_number(a) != _leading_number(b):
        return False
    return is_text_repeat_match(normalize_text(a), normalize_text(b))


def _assign_heading_families(sections: list[dict]) -> dict[int, int]:
    """Map each non-preamble section index to a family id (the index of the
    section that first introduced that heading's fuzzy-normalized text).

    A family id equal to its own index means that section is its family's
    first occurrence -- a real section boundary. Any other section sharing
    that family id is a later, repeated occurrence of a running heading.
    """
    reps: list[tuple[int, str]] = []
    family_id_by_section: dict[int, int] = {}
    for i, sec in enumerate(sections):
        if i == 0 and sec["heading"] == "(preamble)":
            continue
        heading = sec["heading"]
        matched_family = None
        for rep_idx, rep_heading in reps:
            if _headings_match(heading, rep_heading):
                matched_family = rep_idx
                break
        if matched_family is None:
            reps.append((i, heading))
            family_id_by_section[i] = i
        else:
            family_id_by_section[i] = matched_family
    return family_id_by_section


def _running_subtext_drop_set(sections: list[dict], family_id_by_section: dict[int, int]) -> set[int]:
    """Section indices whose first content line is running subtext to drop.

    A line immediately following a running-header occurrence is dropped only
    if it independently repeats (fuzzy-matched) under other occurrences of the
    same heading family; it is always kept under the family's first occurrence.
    """
    family_members: dict[int, list[int]] = {}
    for idx, fam in family_id_by_section.items():
        family_members.setdefault(fam, []).append(idx)

    drop: set[int] = set()
    for fam, members in family_members.items():
        if len(members) < 2:
            continue
        members = sorted(members)
        first_lines = {
            idx: next((l for l in sections[idx]["lines"] if l.strip()), None) for idx in members
        }
        base_idx = members[0]
        base_line = first_lines.get(base_idx)
        if not base_line:
            continue
        base_norm = normalize_text(base_line)
        for idx in members[1:]:
            line = first_lines.get(idx)
            if line and is_text_repeat_match(normalize_text(line), base_norm):
                drop.add(idx)
    return drop


def _fold_running_headers(sections: list[dict]) -> list[dict]:
    """Second pass: fold later occurrences of a running heading family into
    the section they interrupt, dropping matched running subtext lines."""
    family_id_by_section = _assign_heading_families(sections)
    subtext_drop = _running_subtext_drop_set(sections, family_id_by_section)

    folded: list[dict] = []
    open_section: dict | None = None
    for i, sec in enumerate(sections):
        if i == 0 and sec["heading"] == "(preamble)":
            open_section = {"heading": sec["heading"], "level": sec["level"], "lines": list(sec["lines"])}
            folded.append(open_section)
            continue

        lines = list(sec["lines"])
        if i in subtext_drop:
            new_lines = []
            dropped = False
            for line in lines:
                if not dropped and line.strip():
                    dropped = True
                    continue
                new_lines.append(line)
            lines = new_lines

        is_first_occurrence = family_id_by_section[i] == i
        if is_first_occurrence or open_section is None:
            open_section = {"heading": sec["heading"], "level": sec["level"], "lines": lines}
            folded.append(open_section)
        else:
            open_section["lines"].extend(lines)
    return folded


def _parse_sections(markdown: str) -> list[dict]:
    """Split markdown into sections keyed by H2/H3 headings, folding later
    occurrences of a repeated running-header family into the section they
    interrupt (see design.md Decision 3)."""
    raw_sections = _split_heading_stream(markdown)
    folded = _fold_running_headers(raw_sections)
    sections = []
    for s in folded:
        text = "\n".join(s["lines"]).strip()
        sections.append({"heading": s["heading"], "level": s["level"], "text": text})
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
