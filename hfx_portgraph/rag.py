"""Chroma + Ollama naive RAG over parent-child chunks."""

from __future__ import annotations

import json
from pathlib import Path

import ollama

from hfx_portgraph.chunk import load_chunks
from hfx_portgraph.paths import (
    CHAT_MODEL,
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBED_MODEL,
    GOLDEN_PATH,
    chunks_path_for,
    v1_present_reports,
)


def _chroma_client():
    import chromadb
    from chromadb.config import Settings

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def _embed(texts: list[str], prefix: str = "") -> list[list[float]]:
    vectors: list[list[float]] = []
    try:
        for text in texts:
            embed_text = prefix + text
            # Prefer newer embed() API; fall back to embeddings().
            if hasattr(ollama, "embed"):
                resp = ollama.embed(model=EMBED_MODEL, input=embed_text)
                if isinstance(resp, dict):
                    emb = resp.get("embeddings") or resp.get("embedding")
                    if isinstance(emb, list) and emb and isinstance(emb[0], list):
                        vectors.append(emb[0])
                    else:
                        vectors.append(emb)
                else:
                    emb = getattr(resp, "embeddings", None) or getattr(resp, "embedding")
                    vectors.append(emb[0] if emb and isinstance(emb[0], list) else emb)
            else:
                resp = ollama.embeddings(model=EMBED_MODEL, prompt=embed_text)
                if isinstance(resp, dict):
                    vectors.append(resp["embedding"])
                else:
                    vectors.append(resp.embedding)
    except ConnectionError as exc:
        raise SystemExit(
            "Cannot reach Ollama. Install/start it, then:\n"
            f"  ollama pull {EMBED_MODEL}\n"
            f"  ollama pull {CHAT_MODEL}\n"
            "See docs/phase-1.md"
        ) from exc
    return vectors


# Gate is a hardcoded startswith check, not a model->prefix-scheme registry,
# because only one prefix convention is supported today. If a second
# convention shows up, replace this with the small local registry sketched
# in design.md Decision 4 instead of adding another branch here.
def _embed_documents(texts: list[str]) -> list[list[float]]:
    prefix = "search_document: " if EMBED_MODEL.startswith("nomic-embed") else ""
    return _embed(texts, prefix=prefix)


def _embed_query(text: str) -> list[float]:
    prefix = "search_query: " if EMBED_MODEL.startswith("nomic-embed") else ""
    return _embed([text], prefix=prefix)[0]


def index_reports(report_ids: list[str], *, reset: bool = False) -> int:
    """Index child chunks for the given report ids. Returns child count."""
    client = _chroma_client()
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    children: list[dict] = []
    parents: dict[str, dict] = {}
    for rid in report_ids:
        path = chunks_path_for(rid)
        if not path.exists():
            raise FileNotFoundError(path)
        for rec in load_chunks(rid):
            if rec.get("role") == "parent":
                parents[rec["chunk_id"]] = rec
            elif rec.get("role") == "child":
                children.append(rec)

    if not children:
        return 0

    # Upsert in batches
    batch = 32
    total = 0
    for i in range(0, len(children), batch):
        chunk = children[i : i + batch]
        ids = [c["chunk_id"] for c in chunk]
        docs = [c["text"] for c in chunk]
        metadatas = [
            {
                "report_id": c.get("report_id") or "",
                "parent_id": c.get("parent_id") or "",
                "year": str(c.get("year") or ""),
                "section": (c.get("section") or "")[:200],
                "heading": (c.get("heading") or "")[:200],
                "page_start": str(c.get("page_start") if c.get("page_start") is not None else ""),
                "page_end": str(c.get("page_end") if c.get("page_end") is not None else ""),
            }
            for c in chunk
        ]
        embeddings = _embed_documents(docs)
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        total += len(chunk)
    return total


def index_v1(*, reset: bool = False) -> int:
    ids = [r["id"] for r in v1_present_reports()]
    # Only those with chunk files
    ids = [i for i in ids if chunks_path_for(i).exists()]
    return index_reports(ids, reset=reset)


def _parent_text_for(meta: dict) -> str | None:
    parent_id = meta.get("parent_id")
    report_id = meta.get("report_id")
    if parent_id and report_id and chunks_path_for(report_id).exists():
        for rec in load_chunks(report_id):
            if rec.get("chunk_id") == parent_id:
                return rec.get("text")
    return None


def _hits_from_chroma_result(result: dict) -> list[dict]:
    """Build the standard hit shape (chunk_id, text, distance, metadata,
    parent_text) from a raw `collection.query()` result. Shared by `retrieve()`
    and the typed retrieval functions in `retrieval_tools.py` so parent-text
    lookup logic lives in exactly one place."""
    hits: list[dict] = []
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for i, cid in enumerate(ids):
        meta = metas[i] or {}
        hits.append(
            {
                "chunk_id": cid,
                "text": docs[i],
                "distance": dists[i] if i < len(dists) else None,
                "metadata": meta,
                "parent_text": _parent_text_for(meta),
            }
        )
    return hits


def retrieve(question: str, *, n_results: int = 6) -> list[dict]:
    client = _chroma_client()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    if collection.count() == 0:
        return []
    q_emb = _embed_query(question)
    result = collection.query(query_embeddings=[q_emb], n_results=min(n_results, collection.count()))
    return _hits_from_chroma_result(result)


def _format_context(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        meta = h["metadata"]
        cite = (
            f"chunk_id={h['chunk_id']}; report={meta.get('report_id')}; "
            f"section={meta.get('section')}; page_start={meta.get('page_start') or 'unknown'}"
        )
        parent = h.get("parent_text") or ""
        body = h.get("text") or ""
        blocks.append(
            f"[{cite}]\nCHILD:\n{body}\n\nPARENT SECTION:\n{parent[:4000]}"
        )
    return "\n\n----\n\n".join(blocks)


def ask(question: str, *, n_results: int = 6) -> dict:
    hits = retrieve(question, n_results=n_results)
    if not hits:
        return {
            "question": question,
            "status": "insufficient_evidence",
            "answer": "I don't know — no supporting chunks were retrieved from the local index.",
            "citations": [],
            "hits": [],
        }

    context = _format_context(hits)
    system = (
        "You answer questions about Port of Halifax reports using ONLY the provided evidence. "
        "Every factual claim MUST include a citation in the form "
        "[chunk_id=...; page_start=...; section=...]. "
        "If the evidence is insufficient, say you don't know and do not invent numbers."
    )
    user = f"Question: {question}\n\nEvidence:\n{context}"
    try:
        resp = ollama.chat(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except ConnectionError as exc:
        raise SystemExit(
            "Cannot reach Ollama for chat. Install/start it, then:\n"
            f"  ollama pull {CHAT_MODEL}\n"
            "See docs/phase-1.md"
        ) from exc
    if isinstance(resp, dict):
        answer = resp["message"]["content"]
    else:
        answer = resp.message.content

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
        # Model failed to cite — treat as soft insufficiency warning in payload
        status = "answer_uncited"
    else:
        status = "ok"

    return {
        "question": question,
        "status": status,
        "answer": answer,
        "citations": citations,
        "hits": [{"chunk_id": h["chunk_id"], "distance": h.get("distance")} for h in hits],
    }


def load_golden_item(item_id: str) -> dict:
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("id") == item_id:
                return obj
    raise KeyError(item_id)
