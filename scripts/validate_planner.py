#!/usr/bin/env python3
"""Task 2.4 -- planner node validation.

Runs `agent.py::plan_question()` (planner prompt + lenient JSON parsing +
retry/fallback, no retrieval) directly against a handful of
`evals/golden.jsonl` items spanning single-doc, multi-hop, year-collision,
and metric-vs-entity-only shapes, and compares each produced plan to that
item's own `expected_evidence`. Informal fixture check per design.md's
migration plan step 2 -- not a pass/fail gate, since `llama3.1` 8B's
structured-output variance is an accepted project risk (design.md Risks).

Usage: .venv/bin/python scripts/validate_planner.py
"""

from __future__ import annotations

import json

from hfx_portgraph.agent import plan_question
from hfx_portgraph.paths import GOLDEN_PATH

ITEM_IDS = ["gq-001", "gq-003", "gq-012", "gq-019", "gq-024"]


def _load_items(ids: list[str]) -> list[dict]:
    wanted = set(ids)
    items = []
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj["id"] in wanted:
                items.append(obj)
    return items


def _compare(expected: dict, produced: dict) -> dict:
    def _set_overlap(key: str) -> dict:
        exp = set(expected.get(key) or [])
        got = set(produced.get(key) or [])
        return {"expected": sorted(exp), "produced": sorted(got), "missing": sorted(exp - got), "extra": sorted(got - exp)}

    return {"years": _set_overlap("years"), "report_ids": _set_overlap("report_ids")}


def main() -> int:
    items = _load_items(ITEM_IDS)
    results = []
    for item in items:
        plan = plan_question(item["question"])
        comparison = _compare(item["expected_evidence"], plan)
        results.append({"id": item["id"], "question": item["question"], "plan": plan, "comparison": comparison})

        print(f"## {item['id']}")
        print(f"question: {item['question']}")
        print(f"expected: years={item['expected_evidence'].get('years')} report_ids={item['expected_evidence'].get('report_ids')}")
        print(f"produced: years={plan['years']} report_ids={plan['report_ids']} metrics={plan['metrics']} entities={plan['entities']}")
        yc = comparison["years"]
        rc = comparison["report_ids"]
        print(f"year match: missing={yc['missing']} extra={yc['extra']}")
        print(f"report_id match: missing={rc['missing']} extra={rc['extra']}")
        print()

    full_year_match = sum(1 for r in results if not r["comparison"]["years"]["missing"])
    print(f"{full_year_match}/{len(results)} items had no missing years in the produced plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
