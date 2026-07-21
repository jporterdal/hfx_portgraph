#!/usr/bin/env python3
"""Map publisher PDF filenames (from porthalifax.ca) → corpus/raw names.

Browser downloads keep WordPress names like:
  WEB-medium-res-Port-ENGLISH-2023-AnnualReport-May29-2024.pdf
This script renames/copies them to:
  2023_annual_en.pdf

Mapping is driven by:
  1. corpus/catalog.yaml (basename of each source_url)
  2. PUBLISHER_ALIASES below (Wayback reports-page labels + known uploads)
  3. Light heuristics for leftover annual/financials-looking names

Usage (dry-run by default):
  python scripts/map_corpus_filenames.py ~/Downloads
  python scripts/map_corpus_filenames.py ~/Downloads --apply
  python scripts/map_corpus_filenames.py --print-map
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "corpus" / "catalog.yaml"
RAW_DIR = ROOT / "corpus" / "raw"

# Publisher basename (lowercase) → corpus filename.
# Anchored to English reports-page labels from Wayback 2024-12-14 where possible.
# report_type may be a descriptive slug (not only annual|financials|other) so
# multiple non-core docs in the same calendar year do not collide.
PUBLISHER_ALIASES: dict[str, str] = {
    # --- v1-era / catalog peers (also covered by catalog.yaml URLs) ---
    # (catalog entries win via URL basename; aliases here are redundant safety nets)
    # --- Historical financials (page label → year) ---
    "6768hpafinancialsdec3107eng.pdf": "2007_financials_en.pdf",  # 2007 Financial Statements
    "pa_financialsproof2.pdf": "2008_financials_en.pdf",  # 2008 Financial Statements
    "englishfinancials.pdf": "2009_financials_en.pdf",  # 2009 Financial Statements
    "final2012hpaifrsfsenglish.pdf": "2012_financials_en.pdf",  # 2012 Consolidated Financial Statements
    "hpa-2017_eng.pdf": "2017_financials_en.pdf",  # 2017 Consolidated Financial Statements
    "final-fs-hpa.pdf": "2018_financials_en.pdf",  # 2018 Consolidated Financial Statements
    # --- Annual / stakeholder-style ---
    # Filename says AR_2012; reports page labels this row "2011 Stakeholder Report".
    "hpa_ar_2012_lr.pdf": "2011_annual_en.pdf",
    # --- Other / topical (descriptive report_type slugs) ---
    "draft-hpa-agm-may-22-2019-meeting-minutes.pdf": "2019_agm_minutes_en.pdf",
    "hpa-corporate-statement-2020.pdf": "2020_corporate_statement_en.pdf",
    "hpa-report-2023-fighting-against-forced-labour-and-child-labour-in-supply-chains-eng.pdf": (
        "2023_forced_labour_en.pdf"
    ),
    "port-of-halifax_strategic-plan-summary_january-31-2019-v.3.pdf": "2019_strategic_plan_en.pdf",
    # Sustainability: reports-page period, corpus year = end year of the span.
    # HPASustainabilityReportNov282018 is labeled "2017 Sustainability Report".
    "hpasustainabilityreportnov282018.pdf": "2017_sustainability_en.pdf",
    "pohsustainabilityreport20182019.pdf": "2019_sustainability_en.pdf",  # 2018–2019
    "hpa-2020-2021-sustainability-report-final_june-23-2022.pdf": "2021_sustainability_en.pdf",  # 2020–2021
    "port-halifax-sustainability-report-2022-23_eng.pdf": "2023_sustainability_en.pdf",  # 2022–23
}


def corpus_filename(entry: dict) -> str:
    return f"{entry['year']}_{entry['report_type']}_{entry['language']}.pdf"


def basename_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = unquote(urlparse(url).path)
    name = Path(path).name
    return name or None


def load_publisher_map() -> dict[str, str]:
    """Return publisher_basename_lower → corpus_filename."""
    pub_to_corpus: dict[str, str] = dict(PUBLISHER_ALIASES)

    with CATALOG_PATH.open(encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    for entry in catalog["reports"]:
        base = basename_from_url(entry.get("source_url"))
        if base:
            pub_to_corpus[base.lower()] = corpus_filename(entry)

    return pub_to_corpus


def heuristic_guess(name: str) -> str | None:
    """Best-effort guess when basename is not in the explicit map."""
    stem = Path(name).stem
    lower = stem.lower()

    # Prefer two-year sustainability spans → single end-year corpus name.
    span = re.search(r"(20\d{2})\s*[-_]?\s*(20\d{2}|[0-9]{2})", stem)
    if span and re.search(r"sustainab", lower):
        y1, y2 = span.group(1), span.group(2)
        if len(y2) == 2:
            y2 = y1[:2] + y2
        return f"{y2}_sustainability_en.pdf"

    year_match = re.search(r"(20\d{2})", stem)
    if not year_match:
        # Two-digit year in Dec3107-style financials names
        m07 = re.search(r"dec\s*31\s*0?(\d{2})", lower)
        if m07 and re.search(r"financial", lower):
            yy = int(m07.group(1))
            year = 1900 + yy if yy >= 90 else 2000 + yy
            return f"{year}_financials_en.pdf"
        return None
    year = year_match.group(1)

    if re.search(r"financial|statements|\bfs\b|_fs_|-fs-", lower):
        rtype = "financials"
    elif re.search(r"annual|stakeholder|annualreport|\b_ar_|\bar_", lower):
        rtype = "annual"
    elif re.search(r"sustainab", lower):
        rtype = "sustainability"
    elif re.search(r"agm|minutes", lower):
        rtype = "agm_minutes"
    elif re.search(r"strategic", lower):
        rtype = "strategic_plan"
    elif re.search(r"forced.?labour|forced.?labor|child.?labour|child.?labor", lower):
        rtype = "forced_labour"
    elif re.search(r"corporate.?statement", lower):
        rtype = "corporate_statement"
    else:
        return None

    if re.search(r"french|fran[cç]ais|_fr\b|-fr\b", lower):
        lang = "fr"
    else:
        lang = "en"

    return f"{year}_{rtype}_{lang}.pdf"


def resolve_target(path: Path, pub_map: dict[str, str]) -> str | None:
    key = path.name.lower()
    if key in pub_map:
        return pub_map[key]
    return heuristic_guess(path.name)


def print_map(pub_map: dict[str, str]) -> None:
    print("Publisher basename → corpus filename\n")
    for src, dst in sorted(pub_map.items(), key=lambda kv: (kv[1], kv[0])):
        print(f"  {src}")
        print(f"    → {dst}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "downloads_dir",
        nargs="?",
        type=Path,
        help="Folder containing browser-downloaded PDFs (e.g. ~/Downloads)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy matched files into corpus/raw/ (default is dry-run)",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="With --apply, move instead of copy",
    )
    parser.add_argument(
        "--print-map",
        action="store_true",
        help="Print publisher→corpus map and exit",
    )
    args = parser.parse_args()

    pub_map = load_publisher_map()

    if args.print_map:
        print_map(pub_map)
        return 0

    if not args.downloads_dir:
        parser.error("downloads_dir is required unless --print-map")

    src_dir = args.downloads_dir.expanduser().resolve()
    if not src_dir.is_dir():
        print(f"Not a directory: {src_dir}", file=sys.stderr)
        return 1

    pdfs = sorted({*src_dir.glob("*.pdf"), *src_dir.glob("*.PDF")})
    if not pdfs:
        print(f"No PDFs in {src_dir}")
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    matched = 0
    unmatched: list[Path] = []

    print(f"{'APPLY' if args.apply else 'DRY-RUN'} mapping from {src_dir}\n")

    for path in pdfs:
        target_name = resolve_target(path, pub_map)
        if not target_name:
            unmatched.append(path)
            continue

        dest = RAW_DIR / target_name
        how = "move" if args.move else "copy"
        print(f"  {path.name}")
        print(f"    → {dest.relative_to(ROOT)}  ({how if args.apply else 'would ' + how})")

        if args.apply:
            if dest.exists():
                print("    ! exists, skipping")
            elif args.move:
                shutil.move(str(path), str(dest))
            else:
                shutil.copy2(path, dest)
        matched += 1

    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}) — rename manually or extend PUBLISHER_ALIASES:")
        for path in unmatched:
            guess = heuristic_guess(path.name)
            hint = f"  (heuristic: {guess})" if guess else ""
            print(f"  - {path.name}{hint}")

    print(f"\nMatched: {matched}/{len(pdfs)}")
    if args.apply and matched:
        print("Next: python scripts/fetch_corpus.py --manifest-only")
        print("      python scripts/validate_phase0.py")
    return 0 if matched else 2


if __name__ == "__main__":
    raise SystemExit(main())
