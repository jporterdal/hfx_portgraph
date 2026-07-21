#!/usr/bin/env python3
"""Fetch Port of Halifax report PDFs: live URL → Wayback → leave gaps for manual drop.

Usage:
  python scripts/fetch_corpus.py
  python scripts/fetch_corpus.py --manifest-only   # rebuild manifest from catalog + corpus/raw
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "corpus" / "catalog.yaml"
RAW_DIR = ROOT / "corpus" / "raw"
MANIFEST_PATH = ROOT / "corpus" / "manifest.yaml"

USER_AGENT = "hfx-portgraph/0.1 (+local corpus acquisition; respectful public PDF fetch)"


def load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def filename_for(entry: dict) -> str:
    return f"{entry['year']}_{entry['report_type']}_{entry['language']}.pdf"


def wayback_candidates(source_url: str, timestamp: str, client: httpx.Client) -> list[str]:
    """Build Wayback URLs to try: fixed snapshot, then availability API hit."""
    urls = [
        f"https://web.archive.org/web/{timestamp}id_/{source_url}",
        f"https://web.archive.org/web/{timestamp}/{source_url}",
    ]
    try:
        resp = client.get(
            "https://archive.org/wayback/available",
            params={"url": source_url},
            timeout=30.0,
        )
        if resp.status_code == 200:
            snap = resp.json().get("archived_snapshots", {}).get("closest")
            if snap and snap.get("available") and snap.get("url"):
                archived = snap["url"]
                # Prefer id_ form when we can derive it.
                if "/web/" in archived and "id_/" not in archived:
                    urls.append(archived.replace("/web/", "/web/", 1))
                    # Insert id_ after timestamp: /web/TS/http → /web/TSid_/http
                    parts = archived.split("/web/", 1)
                    if len(parts) == 2:
                        ts_and_rest = parts[1]
                        ts = ts_and_rest.split("/", 1)[0]
                        rest = ts_and_rest.split("/", 1)[1] if "/" in ts_and_rest else ""
                        urls.append(f"https://web.archive.org/web/{ts}id_/{rest}")
                urls.append(archived)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  ! wayback availability lookup failed: {exc}")
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def is_pdf_bytes(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def try_download(client: httpx.Client, url: str) -> bytes | None:
    try:
        resp = client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        print(f"  ! request error: {exc}")
        return None
    if resp.status_code != 200:
        print(f"  ! HTTP {resp.status_code} for {url}")
        return None
    if not is_pdf_bytes(resp.content):
        ctype = resp.headers.get("content-type", "")
        print(f"  ! not a PDF (content-type={ctype!r}, size={len(resp.content)})")
        return None
    return resp.content


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_one(client: httpx.Client, entry: dict, timestamp: str, force: bool) -> dict:
    """Return a manifest row for this catalog entry."""
    dest_name = filename_for(entry)
    dest = RAW_DIR / dest_name
    source_url = entry.get("source_url")
    notes = entry.get("notes")

    row = {
        "id": entry["id"],
        "year": entry["year"],
        "report_type": entry["report_type"],
        "language": entry["language"],
        "source_url": source_url,
        "filename": dest_name,
        "status": "missing",
    }
    if notes:
        row["notes"] = notes

    if dest.exists() and dest.stat().st_size > 0 and not force:
        if is_pdf_bytes(dest.read_bytes()[:8]):
            row["status"] = "present"
            row["sha256"] = sha256_file(dest)
            print(f"= skip existing {dest_name}")
            return row
        print(f"! existing file is not a PDF, re-fetching: {dest_name}")

    if not source_url:
        print(f"- {entry['id']}: no source_url (manual browser required)")
        return row

    print(f"> {entry['id']}")
    print(f"  try live: {source_url}")
    data = try_download(client, source_url)
    used_url = source_url

    if data is None:
        candidates = []
        if entry.get("wayback_url"):
            candidates.append(entry["wayback_url"])
        candidates.extend(wayback_candidates(source_url, timestamp, client))
        for wb in candidates:
            print(f"  try wayback: {wb}")
            data = try_download(client, wb)
            if data is not None:
                used_url = wb
                break

    if data is None:
        print(f"  × failed — place {dest_name} in corpus/raw/ manually, then re-run")
        return row

    dest.write_bytes(data)
    row["status"] = "present"
    row["filename"] = dest_name
    row["source_url"] = used_url if used_url.startswith("https://web.archive.org") else source_url
    row["fetched_from"] = used_url
    row["sha256"] = sha256_file(dest)
    print(f"  ✓ wrote {dest_name} ({len(data)} bytes, sha256={row['sha256'][:12]}…)")
    return row


def build_manifest_from_disk(catalog: dict) -> list[dict]:
    """Rebuild manifest without network: catalog + files already in corpus/raw."""
    rows = []
    for entry in catalog["reports"]:
        dest_name = filename_for(entry)
        dest = RAW_DIR / dest_name
        row = {
            "id": entry["id"],
            "year": entry["year"],
            "report_type": entry["report_type"],
            "language": entry["language"],
            "source_url": entry.get("source_url"),
            "filename": dest_name,
            "status": "missing",
        }
        if entry.get("notes"):
            row["notes"] = entry["notes"]
        if dest.exists() and dest.stat().st_size > 0 and is_pdf_bytes(dest.read_bytes()[:8]):
            row["status"] = "present"
            row["sha256"] = sha256_file(dest)
        rows.append(row)
    return rows


def write_manifest(rows: list[dict]) -> None:
    payload = {
        "version": 1,
        "reports": rows,
    }
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    present = sum(1 for r in rows if r["status"] == "present")
    print(f"\nWrote {MANIFEST_PATH} ({present}/{len(rows)} present)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Rebuild manifest.yaml from catalog + corpus/raw without downloading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when a local PDF already exists",
    )
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        print(f"Missing catalog: {CATALOG_PATH}", file=sys.stderr)
        return 1

    catalog = load_catalog()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = str(catalog.get("wayback_timestamp", "20241214192351"))

    if args.manifest_only:
        rows = build_manifest_from_disk(catalog)
        write_manifest(rows)
        return 0

    rows: list[dict] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(120.0, connect=30.0),
    ) as client:
        for entry in catalog["reports"]:
            rows.append(fetch_one(client, entry, timestamp, force=args.force))

    write_manifest(rows)
    missing = [r["id"] for r in rows if r["status"] != "present"]
    if missing:
        print("\nMissing (manual browser fallback):")
        for mid in missing:
            print(f"  - {mid}")
        print("See corpus/README.md for rebuild steps.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
