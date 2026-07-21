"""CLI entrypoints for parse / chunk / index / ask."""

from __future__ import annotations

import argparse
import json
import sys

from hfx_portgraph.chunk import chunk_report
from hfx_portgraph.parse import parse_report
from hfx_portgraph.paths import v1_present_reports
from hfx_portgraph.rag import ask, index_reports, index_v1, load_golden_item


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-id", action="append", dest="report_ids", help="Report id(s)")
    parser.add_argument(
        "--v1-batch",
        action="store_true",
        help="Process all present annual/financials from the manifest",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifacts")


def _resolve_ids(args: argparse.Namespace) -> list[str]:
    if args.v1_batch:
        return [r["id"] for r in v1_present_reports()]
    if args.report_ids:
        return args.report_ids
    raise SystemExit("Provide --report-id and/or --v1-batch")


def parse_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse corpus PDFs with Docling")
    _add_common(parser)
    args = parser.parse_args(argv)
    ids = _resolve_ids(args)
    for rid in ids:
        out = parse_report(rid, force=args.force)
        print(f"✓ parsed {rid} → {out}")
    return 0


def chunk_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunk parsed Markdown into parent/child JSONL")
    _add_common(parser)
    args = parser.parse_args(argv)
    ids = _resolve_ids(args)
    for rid in ids:
        out = chunk_report(rid, force=args.force)
        print(f"✓ chunked {rid} → {out}")
    return 0


def index_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embed child chunks into local Chroma via Ollama")
    _add_common(parser)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate collection")
    args = parser.parse_args(argv)
    if args.v1_batch and not args.report_ids:
        n = index_v1(reset=args.reset)
    else:
        ids = _resolve_ids(args)
        n = index_reports(ids, reset=args.reset)
    print(f"✓ indexed {n} child chunks")
    return 0


def ask_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask a question with cited naive RAG")
    parser.add_argument("question", nargs="?", help="Question text")
    parser.add_argument("--golden", help="Golden item id (uses its question field)")
    parser.add_argument("-k", type=int, default=6, help="Retriever top-k")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args(argv)

    if args.golden:
        item = load_golden_item(args.golden)
        question = item["question"]
        print(f"# golden {args.golden}\n", file=sys.stderr)
    elif args.question:
        question = args.question
    else:
        parser.error("Provide a question or --golden ID")

    result = ask(question, n_results=args.k)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"status: {result['status']}\n")
        print(result["answer"])
        print("\n--- citations ---")
        for c in result["citations"]:
            print(f"- {c}")
    return 0 if result["status"] in {"ok", "insufficient_evidence", "answer_uncited"} else 1


if __name__ == "__main__":
    raise SystemExit(parse_main())
