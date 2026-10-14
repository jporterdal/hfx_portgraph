"""LangGraph plan -> retrieve -> critique -> answer loop (Phase 2).

Decomposes a question into a structured evidence plan, dispatches
deterministic (non-tool-calling) calls into `retrieval_tools.py` per plan
slot, checks coverage before answering, and synthesizes a cited answer --
addressing the naive-RAG ceiling `evals/phase1_baseline.md` documents for
multi-year / multi-hop questions.

Additive only: `rag.py`'s `retrieve()`/`ask()` and the `hfx-ask` CLI are
unchanged. See openspec/changes/langgraph-plan-critique-loop/design.md.
"""

from __future__ import annotations

import json
from typing import TypedDict

import ollama
from langgraph.graph import END, StateGraph

from hfx_portgraph.paths import CHAT_MODEL, v1_present_reports
from hfx_portgraph.rag import _format_context

DEFAULT_MAX_ITERATIONS = 2
DEFAULT_DISPATCH_CEILING = 12
DEFAULT_N_RESULTS = 6


class Plan(TypedDict):
    years: list[int]
    report_ids: list[str]
    metrics: list[str]
    entities: list[str]


class AgentState(TypedDict, total=False):
    question: str
    max_iterations: int
    dispatch_ceiling: int
    n_results: int
    plan: Plan
    evidence: dict[str, list[dict]]
    gaps: list[dict]
    iteration: int
    answer: str
    citations: list[dict]
    status: str


def _empty_plan() -> Plan:
    return {"years": [], "report_ids": [], "metrics": [], "entities": []}


# --- JSON extraction (task 2.2) -------------------------------------------


def extract_json_object(text: str) -> dict | None:
    """Extract the first well-formed `{...}` block from a model response,
    tolerating leading/trailing prose (e.g. "Here is the plan: {...}")."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def _chat_content(resp) -> str:
    if isinstance(resp, dict):
        return resp["message"]["content"]
    return resp.message.content


# --- Planner node (2.1-2.3) -------------------------------------------------

_PLANNER_SYSTEM = (
    "You decompose a question about Port of Halifax annual/financial reports into a "
    "structured evidence plan. Do NOT answer the question and do NOT retrieve or cite "
    "anything -- only identify what evidence would be needed to answer it.\n\n"
    "Respond with a JSON object with exactly these keys:\n"
    '  "years": a list of 4-digit years (as integers) the question needs evidence from\n'
    '  "report_ids": a list of report ids (e.g. "2022_annual_en", "2023_financials_en") '
    "if a specific report is named or clearly implied, else an empty list\n"
    '  "metrics": a list of short, lowercase, underscore-separated financial/operational '
    'metric phrases (e.g. "operating_income", "container_throughput"), else an empty list\n'
    '  "entities": a list of short, lowercase, underscore-separated topic/entity phrases '
    '(e.g. "strategic_initiatives"), else an empty list\n\n'
    "Use an empty list for any key with nothing to add. Do not invent years or reports "
    "the question does not ask about."
)

_PLANNER_RETRY_SYSTEM = _PLANNER_SYSTEM + "\n\nRespond with ONLY the JSON object -- no other text."


def _call_planner_model(question: str, *, strict: bool) -> dict | None:
    system = _PLANNER_RETRY_SYSTEM if strict else _PLANNER_SYSTEM
    resp = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Question: {question}"},
        ],
    )
    return extract_json_object(_chat_content(resp))


def _valid_report_ids() -> set[str]:
    return {r["id"] for r in v1_present_reports()}


def normalize_plan(raw: dict) -> Plan:
    def _str_list(key: str) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return []
        return [str(v) for v in value if isinstance(v, (str, int, float))]

    years: list[int] = []
    for y in raw.get("years") or []:
        try:
            years.append(int(y))
        except (TypeError, ValueError):
            continue

    # An 8B model asked to name report ids sometimes drops the year prefix
    # (e.g. "annual_en" instead of "2022_annual_en"). A hallucinated id fed
    # straight into the retriever's `$in` filter would silently zero out
    # results rather than degrade gracefully, so unknown ids are dropped
    # here -- the year-scoped dispatch path still covers the same ground
    # without a report_id constraint.
    report_ids = [r for r in _str_list("report_ids") if r in _valid_report_ids()]

    return {
        "years": years,
        "report_ids": report_ids,
        "metrics": _str_list("metrics"),
        "entities": _str_list("entities"),
    }


def fallback_plan(question: str) -> Plan:
    """Decision 3: degrade to a single evidence goal covering the whole
    question, with no year/report constraint, rather than failing the turn."""
    return {"years": [], "report_ids": [], "metrics": [], "entities": [question]}


def plan_question(question: str) -> Plan:
    """Run the planner (with retry-then-fallback) for a bare question,
    independent of graph state -- used directly by validate_planner.py."""
    raw = _call_planner_model(question, strict=False)
    if raw is None:
        raw = _call_planner_model(question, strict=True)
    return normalize_plan(raw) if raw is not None else fallback_plan(question)


def planner_node(state: AgentState) -> dict:
    plan = plan_question(state["question"])
    return {"plan": plan, "iteration": 0, "evidence": {}, "gaps": []}


# --- Retriever node (3.1-3.3) -----------------------------------------------


def _join_terms(*term_lists: list[str]) -> str:
    terms = [t for lst in term_lists for t in lst if t]
    return " ".join(terms)


def build_dispatch_units(
    plan: Plan,
    question: str,
    *,
    ceiling: int,
    only_years: set[int] | None = None,
    only_report_ids: set[str] | None = None,
) -> list[dict]:
    """Turn a plan into a list of dispatch units, each a single-year (or
    single-report_id) call into `retrieve_with_section_filter()` -- kept at
    that granularity deliberately: that function over-fetches and truncates
    to `n_results` *within* one call, so batching multiple years/report_ids
    into one call would let its section re-rank discard whole years/reports
    instead of just demoting notes within one, silently breaking the
    per-year/per-report coverage guarantee `retrieve_by_year`/
    `retrieve_by_report` exist to provide. One unit per (year, report) slot
    preserves that guarantee while still getting the statement-over-note
    preference (design.md Decision 3) that avoids the `year_collision`
    footnote match documented in `evals/phase1_baseline.md`.

    Caps total underlying Chroma queries at `ceiling` (Decision 4): a plan
    with Y years and M metrics would otherwise cost Y*M queries (one call
    per year per metric); when that would exceed the ceiling, collapse to
    one call per year with all metric/entity text joined instead.

    Year-scoped units deliberately do NOT also filter by the plan's
    `report_ids` -- Decision 4 only specifies `report_ids` as a hard filter
    for the no-year dispatch path below. Layering it onto the year path too
    was tried and reverted: a planner that names the wrong report for a
    year (e.g. `2023_annual_en` for an `operating_income` question that
    lives in `2023_financials_en`) turned that into a silent, wrong-report
    retrieval miss reported as "no evidence found" instead of just being a
    slightly noisier top-k -- narrowing by year alone is never less correct
    than narrowing by year+report_id, only broader, so it's the safer
    default when the report_id can't be trusted.

    `only_years`/`only_report_ids`, when given, restrict dispatch to just
    those slots (used by the critic's focused-retry pass for missing slots
    only, rather than re-running the full plan from scratch).

    Each unit carries the plan-slot key (`year:Y` / `report:R`) it was
    built from, so the retriever can file its hits under exactly the key
    the critic checks (design.md Decision 5 amendment).
    """
    years = sorted(set(only_years if only_years is not None else plan["years"]))
    metrics = plan["metrics"]
    entities = plan["entities"]

    if years:
        if metrics and len(years) * len(metrics) <= ceiling:
            return [
                {"kind": "year", "slot": f"year:{y}", "year": y, "report_ids": None, "query": _join_terms([m], entities)}
                for y in years
                for m in metrics
            ]
        # The ceiling is never exceeded, even when the plan has more years
        # than it: only the first `ceiling` years (ascending) go out this
        # pass, and the rest surface as critic gaps for the focused retry.
        # Known limitation: years beyond `ceiling * max_iterations` are never
        # dispatched (design.md Decision 4 amendment).
        joined_query = _join_terms(metrics, entities) or question
        return [
            {"kind": "year", "slot": f"year:{y}", "year": y, "report_ids": None, "query": joined_query}
            for y in years[:ceiling]
        ]

    # Decision 4: metric/entity-only goals with no year dispatch via a bare
    # per-report_id call, scoped to the plan's report_ids (or all v1
    # reports if unspecified) -- one unit per report_id for the same
    # coverage-preservation reason as the per-year case above.
    rids = sorted(only_report_ids) if only_report_ids is not None else (plan["report_ids"] or [r["id"] for r in v1_present_reports()])
    rids = rids[:ceiling]
    query = _join_terms(metrics, entities) or question
    return [{"kind": "report", "slot": f"report:{rid}", "report_id": rid, "query": query} for rid in rids]


def _dispatch_hits(unit: dict, *, n_results: int) -> list[dict]:
    from hfx_portgraph.retrieval_tools import retrieve_with_section_filter

    if unit["kind"] == "year":
        return retrieve_with_section_filter(
            unit["query"], years=[unit["year"]], report_ids=unit["report_ids"], n_results=n_results
        )
    return retrieve_with_section_filter(unit["query"], report_ids=[unit["report_id"]], n_results=n_results)


def _accumulate(
    evidence: dict[str, list[dict]], slot_hits: list[tuple[str, list[dict]]]
) -> dict[str, list[dict]]:
    """Merge each dispatch unit's hits into evidence under that unit's
    plan-slot key -- not a key inferred from hit metadata, which would file
    every v1 chunk under `year:` and never match a report-only plan's
    `report:` slots (design.md Decision 5 amendment)."""
    seen = {h["chunk_id"] for hits_list in evidence.values() for h in hits_list}
    merged = {k: list(v) for k, v in evidence.items()}
    for slot, hits in slot_hits:
        for hit in hits:
            if hit["chunk_id"] in seen:
                continue
            seen.add(hit["chunk_id"])
            merged.setdefault(slot, []).append(hit)
    return merged


def retriever_node(state: AgentState) -> dict:
    plan = state["plan"]
    ceiling = state.get("dispatch_ceiling", DEFAULT_DISPATCH_CEILING)
    n_results = state.get("n_results", DEFAULT_N_RESULTS)

    focus_years = None
    focus_report_ids = None
    if state.get("gaps"):
        year_gaps = {g["value"] for g in state["gaps"] if g["type"] == "year"}
        report_gaps = {g["value"] for g in state["gaps"] if g["type"] == "report"}
        if year_gaps:
            focus_years = year_gaps
        if report_gaps:
            focus_report_ids = report_gaps

    units = build_dispatch_units(
        plan,
        state["question"],
        ceiling=ceiling,
        only_years=focus_years,
        only_report_ids=focus_report_ids,
    )
    slot_hits = [(unit["slot"], _dispatch_hits(unit, n_results=n_results)) for unit in units]

    evidence = _accumulate(state.get("evidence") or {}, slot_hits)
    return {"evidence": evidence}


# --- Critic node (4.1-4.3) ---------------------------------------------------


def _plan_slots(plan: Plan) -> list[dict]:
    if plan["years"]:
        return [{"type": "year", "value": y} for y in plan["years"]]
    if plan["report_ids"]:
        return [{"type": "report", "value": rid} for rid in plan["report_ids"]]
    return []


def _slot_covered(slot: dict, evidence: dict[str, list[dict]]) -> bool:
    if slot["type"] == "year":
        return f"year:{slot['value']}" in evidence
    return f"report:{slot['value']}" in evidence


def find_gaps(plan: Plan, evidence: dict[str, list[dict]]) -> list[dict]:
    return [slot for slot in _plan_slots(plan) if not _slot_covered(slot, evidence)]


def critic_node(state: AgentState) -> dict:
    gaps = find_gaps(state["plan"], state.get("evidence") or {})
    return {"gaps": gaps, "iteration": state.get("iteration", 0) + 1}


def critic_route(state: AgentState) -> str:
    max_iterations = state.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    if state.get("gaps") and state.get("iteration", 0) < max_iterations:
        return "retriever"
    return "synthesizer"


# --- Synthesizer node (5.1-5.4) ----------------------------------------------

_SYNTH_SYSTEM = (
    "You answer questions about Port of Halifax reports using ONLY the provided evidence. "
    "Every factual claim MUST include a citation in the form "
    "[chunk_id=...; page_start=...; section=...]. "
    "If a listed gap has no evidence for a year, explicitly say so (e.g. \"no evidence "
    "found for 2023\") rather than omitting it or inventing a number. "
    "Do not invent numbers."
)

_CITATION_REPAIR_SYSTEM = _SYNTH_SYSTEM + (
    "\n\nYour previous answer did not include any [chunk_id=...] citation tags. "
    "Rewrite the answer so every factual claim carries one, in the exact form "
    "[chunk_id=...; page_start=...; section=...]."
)


def _all_hits(evidence: dict[str, list[dict]]) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    for hits_list in evidence.values():
        for h in hits_list:
            if h["chunk_id"] in seen:
                continue
            seen.add(h["chunk_id"])
            hits.append(h)
    return hits


SYNTH_HITS_PER_SLOT = 4
SYNTH_MAX_HITS = 24


def _synthesis_hits(evidence: dict[str, list[dict]]) -> list[dict]:
    """Cap the evidence handed to the synthesizer prompt: a multi-slot plan
    (e.g. gq-001's 4 years) can accumulate far more hits across slots than
    `rag.py::ask()`'s single-shot n_results=6 ever did, and Ollama's default
    context window silently truncates a prompt that large -- the model then
    answers as if no evidence were provided at all rather than erroring, so
    this isn't optional. Keeps the best `SYNTH_HITS_PER_SLOT` hits (by
    distance) from every slot so every plan target still gets a citation
    opportunity, then truncates the merged, deduped list to
    `SYNTH_MAX_HITS` if still over."""
    hits: list[dict] = []
    seen: set[str] = set()
    for hits_list in evidence.values():
        best = sorted(hits_list, key=lambda h: h.get("distance") if h.get("distance") is not None else float("inf"))
        for h in best[:SYNTH_HITS_PER_SLOT]:
            if h["chunk_id"] in seen:
                continue
            seen.add(h["chunk_id"])
            hits.append(h)
    return hits[:SYNTH_MAX_HITS]


_MAX_NUM_CTX = 32768
_CHARS_PER_TOKEN = 4  # rough heuristic, matches chunk.py's own token-count estimate


def _num_ctx_for(prompt: str) -> int:
    """Size the request's context window to the prompt actually built,
    rounded up to the next power-of-two-ish Ollama bucket, rather than
    trusting the 4096-token default a multi-slot evidence prompt can
    silently exceed."""
    estimated_tokens = len(prompt) // _CHARS_PER_TOKEN
    needed = int(estimated_tokens * 1.5) + 512  # headroom for system prompt + response
    for bucket in (4096, 8192, 16384, 32768):
        if needed <= bucket:
            return bucket
    return _MAX_NUM_CTX


def _gap_description(gap: dict) -> str:
    return f"{gap['type']}={gap['value']}"


def _build_synth_user_message(question: str, hits: list[dict], gaps: list[dict]) -> str:
    context = _format_context(hits)
    message = f"Question: {question}\n\nEvidence:\n{context}"
    if gaps:
        gap_list = ", ".join(_gap_description(g) for g in gaps)
        message += f"\n\nNo evidence was found for these plan targets: {gap_list}."
    return message


def synthesizer_node(state: AgentState) -> dict:
    hits = _synthesis_hits(state.get("evidence") or {})
    gaps = state.get("gaps") or []
    question = state["question"]

    if not hits:
        return {
            "answer": "I don't know — no supporting chunks were retrieved from the local index.",
            "citations": [],
            "status": "insufficient_evidence",
        }

    user = _build_synth_user_message(question, hits, gaps)
    # Ollama loads llama3.1 with a 4096-token context window by default
    # (`ollama ps`), regardless of the model's own much larger native
    # limit; a multi-slot evidence prompt (several years/reports at once,
    # unlike ask()'s single-shot 6-hit prompt) easily exceeds that, and
    # llama.cpp truncates from the front -- silently dropping the question
    # itself, not just trimming evidence. Request a window sized to what
    # was actually assembled instead of hitting that silently.
    num_ctx = _num_ctx_for(user)
    resp = ollama.chat(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": _SYNTH_SYSTEM}, {"role": "user", "content": user}],
        options={"num_ctx": num_ctx},
    )
    answer = _chat_content(resp)

    if "chunk_id=" not in answer.lower():
        repair_resp = ollama.chat(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": _CITATION_REPAIR_SYSTEM},
                {"role": "user", "content": user},
                {"role": "assistant", "content": answer},
                {"role": "user", "content": "Rewrite with citations on every claim."},
            ],
            options={"num_ctx": num_ctx},
        )
        answer = _chat_content(repair_resp)

    citations = [
        {
            "chunk_id": h["chunk_id"],
            "report_id": h["metadata"].get("report_id"),
            "section": h["metadata"].get("section"),
            "page_start": h["metadata"].get("page_start") or None,
        }
        for h in hits
    ]

    lower = answer.lower()
    if "chunk_id=" not in lower and (
        "don't know" in lower or "do not know" in lower or "insufficient" in lower
    ):
        status = "insufficient_evidence"
    elif "chunk_id=" not in lower:
        status = "answer_uncited"
    else:
        status = "ok"

    return {"answer": answer, "citations": citations, "status": status}


# --- Graph wiring (6.1) ------------------------------------------------------


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("critic", critic_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "critic")
    graph.add_conditional_edges("critic", critic_route, {"retriever": "retriever", "synthesizer": "synthesizer"})
    graph.add_edge("synthesizer", END)
    return graph.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_agent(
    question: str,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    dispatch_ceiling: int = DEFAULT_DISPATCH_CEILING,
    n_results: int = DEFAULT_N_RESULTS,
) -> dict:
    """Run the full planner -> retriever -> critic -> synthesizer loop.
    Returns a dict shape-compatible with `rag.py::ask()` (`question`,
    `status`, `answer`, `citations`, `hits`) plus `plan` and `iterations`."""
    initial: AgentState = {
        "question": question,
        "max_iterations": max_iterations,
        "dispatch_ceiling": dispatch_ceiling,
        "n_results": n_results,
    }
    result = _graph().invoke(initial)
    hits = _all_hits(result.get("evidence") or {})
    return {
        "question": question,
        "status": result.get("status", "insufficient_evidence"),
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "hits": [{"chunk_id": h["chunk_id"], "distance": h.get("distance")} for h in hits],
        "plan": result.get("plan", _empty_plan()),
        "iterations": result.get("iteration", 0),
    }
