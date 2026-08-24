"""One-off inspector: print the full `user` message (Question + Evidence) sent
to Ollama by hfx_portgraph.rag.ask(), plus the retrieve() hit list (chunk_id +
embedding distance) behind it, for the first two golden questions
(gq-001, gq-002).

Hooks ollama.chat and rag.retrieve as seen from inside the rag module (no
edits to rag.py). Lets the real calls through afterwards so status/citations
are also printed.

Run from the repo root with the project venv:
    .venv/bin/python scripts/scratch/inspect_rag_prompt.py
"""

from __future__ import annotations

from hfx_portgraph import rag

GOLDEN_IDS = ["gq-001", "gq-002"]

_real_chat = rag.ollama.chat
_real_retrieve = rag.retrieve


def _spy_retrieve(question, *, n_results=6):
    hits = _real_retrieve(question, n_results=n_results)

    print("-" * 100)
    print(f"RETRIEVE: n_results={n_results}, hits={len(hits)}")
    for rank, h in enumerate(hits, start=1):
        meta = h["metadata"]
        print(
            f"  [{rank}] distance={h['distance']:.4f}  chunk_id={h['chunk_id']}  "
            f"report={meta.get('report_id')}  section={meta.get('section')}  "
            f"page_start={meta.get('page_start') or 'unknown'}"
        )

    return hits


def _spy_chat(*, model, messages, **kwargs):
    system_msg, user_msg = messages[0], messages[1]

    print("=" * 100)
    print(f"MODEL: {model}")
    print("-" * 100)
    print("SYSTEM:")
    print(system_msg["content"])
    print("-" * 100)
    print("USER:")
    print(user_msg["content"])
    print(f"\n[user message length: {len(user_msg['content'])} chars]")
    print("=" * 100)

    return _real_chat(model=model, messages=messages, **kwargs)


rag.retrieve = _spy_retrieve
rag.ollama.chat = _spy_chat

for item_id in GOLDEN_IDS:
    item = rag.load_golden_item(item_id)
    question = item["question"]
    print(f"\n\n######## {item_id}: {question} ########\n")

    result = rag.ask(question)

    print("\n--- ask() result summary ---")
    print(f"status: {result['status']}")
    print(f"answer: {result['answer']}")
    print("citations:")
    for c in result["citations"]:
        print(f"  - {c}")

rag.retrieve = _real_retrieve
rag.ollama.chat = _real_chat
