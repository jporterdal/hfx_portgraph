"""Shared paths and manifest helpers for hfx_portgraph."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "corpus"
RAW_DIR = CORPUS_DIR / "raw"
PARSED_DIR = CORPUS_DIR / "parsed"
CHUNKS_DIR = CORPUS_DIR / "chunks"
MANIFEST_PATH = CORPUS_DIR / "manifest.yaml"
GOLDEN_PATH = ROOT / "evals" / "golden.jsonl"
CHROMA_DIR = Path(os.environ.get("HFX_CHROMA_DIR", ROOT / "data" / "chroma"))

EMBED_MODEL = os.environ.get("HFX_EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.environ.get("HFX_CHAT_MODEL", "llama3.1")
COLLECTION_NAME = "hfx_child_chunks"


def load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def report_by_id(report_id: str) -> dict:
    for row in load_manifest().get("reports") or []:
        if row.get("id") == report_id:
            return row
    raise KeyError(f"report id not in manifest: {report_id}")


def v1_present_reports() -> list[dict]:
    rows = []
    for row in load_manifest().get("reports") or []:
        if row.get("status") != "present":
            continue
        if row.get("report_type") not in {"annual", "financials"}:
            continue
        rows.append(row)
    return rows


def pdf_path_for(report: dict) -> Path:
    fn = report.get("filename")
    if not fn:
        raise FileNotFoundError(f"no filename for {report.get('id')}")
    path = RAW_DIR / fn
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def parsed_dir_for(report_id: str) -> Path:
    return PARSED_DIR / report_id


def chunks_path_for(report_id: str) -> Path:
    return CHUNKS_DIR / f"{report_id}.jsonl"
