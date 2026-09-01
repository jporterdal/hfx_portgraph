"""Typed retrieval functions over the existing Chroma child-chunk index.

Wraps `rag.py`'s collection with metadata `where` filtering (year, report_id)
and a section-type-aware re-rank, so callers can target evidence by year,
report, or statement-vs-note section instead of one undifferentiated
similarity search. See openspec/changes/typed-retrieval-tools/design.md.

Additive only: `rag.py`'s `retrieve()`/`ask()` and `cli.py` are unchanged.
"""

from __future__ import annotations

import re

from hfx_portgraph.paths import COLLECTION_NAME, report_by_id, v1_present_reports
from hfx_portgraph.rag import _chroma_client, _embed_query, _hits_from_chroma_result

DEFAULT_N_RESULTS = 6
_SECTION_FETCH_MULTIPLIER = 4


# --- Report-type helpers (manifest-derived; no new Chroma metadata) -------


def report_types_for(report_ids: list[str]) -> dict[str, str]:
    """Resolve `report_type` ('annual'/'financials') per `report_id` from
    `corpus/manifest.yaml`. Raises KeyError naming every id not present in
    the manifest, rather than guessing a type or silently skipping it."""
    types: dict[str, str] = {}
    missing: list[str] = []
    for rid in report_ids:
        try:
            types[rid] = report_by_id(rid).get("report_type")
        except KeyError:
            missing.append(rid)
    if missing:
        raise KeyError(f"report_id(s) not present in corpus/manifest.yaml: {missing}")
    return types


def report_ids_for_type(report_type: str) -> list[str]:
    """Expand a `report_type` ('annual'/'financials') into the matching,
    present `report_id`s via `corpus/manifest.yaml`."""
    return [r["id"] for r in v1_present_reports() if r.get("report_type") == report_type]


# --- Year- and report-scoped retrieval ------------------------------------


def _where_clause(*, year: str | None = None, report_ids: list[str] | None = None) -> dict | None:
    clauses: list[dict] = []
    if year is not None:
        clauses.append({"year": {"$eq": year}})
    if report_ids:
        clauses.append({"report_id": {"$in": list(report_ids)}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _query(collection, q_emb: list[float], *, where: dict | None, n_results: int) -> list[dict]:
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[q_emb],
        n_results=min(n_results, collection.count()),
        where=where,
    )
    return _hits_from_chroma_result(result)


def retrieve_by_year(
    question: str,
    years: list[int | str],
    *,
    report_ids: list[str] | None = None,
    n_results: int = DEFAULT_N_RESULTS,
) -> list[dict]:
    """Embed the query once, then fan out one Chroma query per requested
    year so every year with matching indexed content contributes at least
    one hit, rather than one global top-k letting a single year's passages
    crowd out the rest (design.md Decision 1).

    Chroma stores `year` as a string (`rag.py::index_reports`), so each
    year is cast to `str()` before building the `$eq` filter.
    """
    client = _chroma_client()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    if collection.count() == 0:
        return []
    q_emb = _embed_query(question)

    hits: list[dict] = []
    seen: set[str] = set()
    for year in years:
        where = _where_clause(year=str(year), report_ids=report_ids)
        for hit in _query(collection, q_emb, where=where, n_results=n_results):
            if hit["chunk_id"] in seen:
                continue
            seen.add(hit["chunk_id"])
            hits.append(hit)
    return hits


def retrieve_by_report(
    question: str,
    report_ids: list[str],
    *,
    years: list[int | str] | None = None,
    n_results: int = DEFAULT_N_RESULTS,
) -> list[dict]:
    """Fan out one Chroma query per requested `report_id`, mirroring
    `retrieve_by_year`'s per-year loop, so every requested report_id with
    matching content contributes at least one hit — rather than pooling all
    requested reports into a single ranked list where one report's passages
    can crowd out another's (design.md Decision 7; the same crowding shape
    Decision 1 already fixed for years, extended here to reports).

    If `years` is also given, delegates to `retrieve_by_year`'s per-year
    fan-out (with `report_ids` applied to each per-year query) so the
    multi-year coverage guarantee still holds when both constraints are
    combined (design.md Decision 1; tasks.md 2.3).

    For the previous single-`$in`-query pooled behavior (no per-report
    guarantee), use `retrieve_with_report_filter`.
    """
    if years:
        return retrieve_by_year(question, years, report_ids=report_ids, n_results=n_results)

    client = _chroma_client()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    if collection.count() == 0:
        return []
    q_emb = _embed_query(question)

    hits: list[dict] = []
    seen: set[str] = set()
    for rid in report_ids:
        where = _where_clause(report_ids=[rid])
        for hit in _query(collection, q_emb, where=where, n_results=n_results):
            if hit["chunk_id"] in seen:
                continue
            seen.add(hit["chunk_id"])
            hits.append(hit)
    return hits


def retrieve_with_report_filter(
    question: str,
    report_ids: list[str],
    *,
    n_results: int = DEFAULT_N_RESULTS,
) -> list[dict]:
    """Single Chroma query with `where={"report_id": {"$in": report_ids}}`
    — all requested reports pooled into one ranked list, no per-report
    coverage guarantee. Cheaper than `retrieve_by_report`'s fan-out and
    produces identical results to it for a single `report_id`; prefer this
    when `report_ids` is a scoping filter rather than a set of
    required-coverage groups (design.md Decision 7)."""
    client = _chroma_client()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    if collection.count() == 0:
        return []
    q_emb = _embed_query(question)
    where = _where_clause(report_ids=report_ids)
    return _query(collection, q_emb, where=where, n_results=n_results)


# --- Section-type-aware retrieval -----------------------------------------

# Numbered notes/disclosures (e.g. "17. Comparative figures", "7. PROPERTY
# AND EQUIPMENT") lead with a number label — the same load-bearing signal
# chunk.py's running-header fold treats as note identity (see
# chunk.py::_leading_number).
_NOTE_HEADING_RE = re.compile(r"^\s*\d+[.\)]\s")

# Canonical primary-statement titles only — NOT a bare "statement of" match,
# which would also catch policy headings like "Statement of compliance"
# (an accounting-policy note, not a primary financial statement).
_STATEMENT_HEADING_RE = re.compile(
    r"statement of (earnings|comprehensive income|financial position|"
    r"changes in equity|cash flows|operations)",
    re.IGNORECASE,
)

_SECTION_PRIORITY = {"statement": 0, "other": 1, "note": 2}


def classify_section(heading: str | None) -> str:
    """Heuristically classify a heading/section string as 'note'
    (footnote/disclosure-style heading), 'statement' (primary financial
    statement heading), or 'other' (neither pattern matches).

    A re-ranking signal, not a hard filter — misclassifications are expected
    and logged in the validation note rather than treated as ground truth
    (design.md Decision 3).
    """
    text = heading or ""
    if _NOTE_HEADING_RE.match(text):
        return "note"
    if _STATEMENT_HEADING_RE.search(text):
        return "statement"
    return "other"


def rerank_by_section(hits: list[dict]) -> list[dict]:
    """Stable re-rank: statement-labeled hits first, then unclassified, then
    note/footnote-labeled hits, preserving each group's original relative
    (distance) order."""
    return sorted(
        hits,
        key=lambda h: _SECTION_PRIORITY.get(classify_section(h.get("metadata", {}).get("heading")), 1),
    )


def retrieve_with_section_filter(
    question: str,
    *,
    report_ids: list[str] | None = None,
    years: list[int | str] | None = None,
    n_results: int = DEFAULT_N_RESULTS,
    fetch_k: int | None = None,
) -> list[dict]:
    """Retrieve (optionally year/report-scoped), then re-rank so
    primary-statement-labeled hits are preferred over note/footnote-labeled
    hits when both are present for the same query (design.md Decision 3).

    Over-fetches `fetch_k` candidates (default `n_results *
    _SECTION_FETCH_MULTIPLIER`) before re-ranking and truncating to
    `n_results`, so a demoted note-labeled hit doesn't just get lost — a
    same-content statement-labeled hit further down the raw ranking gets a
    chance to surface instead.
    """
    fetch_k = fetch_k or n_results * _SECTION_FETCH_MULTIPLIER
    if report_ids:
        hits = retrieve_by_report(question, report_ids, years=years, n_results=fetch_k)
    elif years:
        hits = retrieve_by_year(question, years, n_results=fetch_k)
    else:
        from hfx_portgraph.rag import retrieve

        hits = retrieve(question, n_results=fetch_k)
    return rerank_by_section(hits)[:n_results]
