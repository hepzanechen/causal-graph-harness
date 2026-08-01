"""Read-only evidence broker and deterministic scorer for the pioneer cases.

Only ``load_case``, ``search_evidence``, and ``read_evidence`` belong in an
agent sandbox. ``score_answer`` reads the sealed gold directory and must run in
the evaluator process after the agent exits.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
GOLD_DIR = ROOT / "gold"
CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BenchmarkError(ValueError):
    """Raised for malformed case IDs, queries, evidence IDs, or answers."""


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise BenchmarkError(f"expected JSON object in {path.name}")
    return value


def _path_for(directory: Path, case_id: str) -> Path:
    if not CASE_ID_RE.fullmatch(case_id):
        raise BenchmarkError(f"invalid case ID: {case_id!r}")
    path = directory / f"{case_id}.json"
    if not path.is_file():
        raise BenchmarkError(f"unknown case: {case_id}")
    return path


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def list_cases() -> list[dict[str, Any]]:
    """Return public metadata without evidence content or gold labels."""
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        case = _read_json(path)
        cases.append({
            "id": case["id"],
            "title": case["title"],
            "difficulty": case["difficulty"],
            "source_types": case["source_types"],
        })
    return cases


def load_case(case_id: str) -> dict[str, Any]:
    """Return the public prompt and source catalog, but not evidence bodies."""
    case = _read_json(_path_for(CASES_DIR, case_id))
    return {
        "id": case["id"],
        "title": case["title"],
        "difficulty": case["difficulty"],
        "prompt": case["prompt"],
        "source_types": case["source_types"],
        "answer_contract": case["answer_contract"],
    }


def search_evidence(
    case_id: str,
    query: str,
    *,
    source_type: str | None = None,
    component: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search frozen evidence and return metadata plus short excerpts.

    A non-empty query is required so an agent must make an evidence-selection
    decision instead of dumping the entire packet in one call.
    """
    terms = set(_normalize(query).split())
    if not terms:
        raise BenchmarkError("query must contain at least one letter or digit")
    if not 1 <= limit <= 10:
        raise BenchmarkError("limit must be between 1 and 10")

    case = _read_json(_path_for(CASES_DIR, case_id))
    matches: list[tuple[int, dict[str, Any]]] = []
    for item in case["evidence"]:
        if source_type and item["source_type"] != source_type:
            continue
        if component and _normalize(item["component"]) != _normalize(component):
            continue
        searchable = _normalize(" ".join([
            item["component"], item["summary"], item["content"],
            " ".join(item.get("tags", [])),
        ]))
        score = sum(term in searchable.split() for term in terms)
        if score:
            matches.append((score, item))

    matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        {
            "id": item["id"],
            "source_type": item["source_type"],
            "component": item["component"],
            "timestamp": item["timestamp"],
            "summary": item["summary"],
            "excerpt": item["content"][:240],
        }
        for _, item in matches[:limit]
    ]


def read_evidence(case_id: str, evidence_id: str) -> dict[str, Any]:
    """Return one complete frozen evidence record by opaque ID."""
    case = _read_json(_path_for(CASES_DIR, case_id))
    for item in case["evidence"]:
        if item["id"] == evidence_id:
            return dict(item)
    raise BenchmarkError(f"unknown evidence ID for {case_id}: {evidence_id}")


def _root_set(items: Any) -> set[tuple[str, str]]:
    if not isinstance(items, list):
        raise BenchmarkError("root_causes must be a list")
    roots = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("component") or not item.get("fault"):
            raise BenchmarkError("each root cause needs component and fault")
        roots.add((_normalize(item["component"]), _normalize(item["fault"])))
    return roots


def _edge_set(items: Any) -> set[tuple[str, str]]:
    if not isinstance(items, list):
        raise BenchmarkError("causal_chain must be a list")
    edges = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
            raise BenchmarkError("each causal step needs from and to")
        edges.add((_normalize(item["from"]), _normalize(item["to"])))
    return edges


def score_answer(case_id: str, answer: dict[str, Any]) -> dict[str, Any]:
    """Score the top hypothesis against sealed gold labels."""
    hypotheses = answer.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise BenchmarkError("answer must contain at least one hypothesis")
    top = min(hypotheses, key=lambda item: item.get("rank", 10**9))
    predicted_roots = _root_set(top.get("root_causes"))
    predicted_edges = _edge_set(top.get("causal_chain"))

    gold = _read_json(_path_for(GOLD_DIR, case_id))
    gold_roots = _root_set(gold["root_causes"])
    required_edges = _edge_set(gold["required_chain"])
    accepted_edges = _edge_set(gold.get("accepted_chain", gold["required_chain"]))

    cited = top.get("evidence_ids", [])
    if not isinstance(cited, list) or not all(isinstance(item, str) for item in cited):
        raise BenchmarkError("evidence_ids must be a list of strings")
    public = _read_json(_path_for(CASES_DIR, case_id))
    known_ids = {item["id"] for item in public["evidence"]}
    unknown_citations = sorted(set(cited) - known_ids)
    critical = set(gold["critical_evidence_ids"])

    root_match = predicted_roots == gold_roots
    chain_recall = len(predicted_edges & required_edges) / len(required_edges)
    unsupported_edges = predicted_edges - accepted_edges
    evidence_recall = len(set(cited) & critical) / len(critical)
    return {
        "case_id": case_id,
        "root_cause_exact_match": root_match,
        "causal_chain_recall": round(chain_recall, 4),
        "unsupported_chain_edges": len(unsupported_edges),
        "critical_evidence_recall": round(evidence_recall, 4),
        "unknown_evidence_ids": unknown_citations,
        "joint_success": (
            root_match
            and chain_recall == 1.0
            and not unsupported_edges
            and not unknown_citations
        ),
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")

    prompt_parser = subparsers.add_parser("prompt")
    prompt_parser.add_argument("case_id")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("case_id")
    search_parser.add_argument("query")
    search_parser.add_argument("--source-type")
    search_parser.add_argument("--component")
    search_parser.add_argument("--limit", type=int, default=5)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("case_id")
    read_parser.add_argument("evidence_id")

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("case_id")
    score_parser.add_argument("answer_file", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            _print_json(list_cases())
        elif args.command == "prompt":
            _print_json(load_case(args.case_id))
        elif args.command == "search":
            _print_json(search_evidence(
                args.case_id,
                args.query,
                source_type=args.source_type,
                component=args.component,
                limit=args.limit,
            ))
        elif args.command == "read":
            _print_json(read_evidence(args.case_id, args.evidence_id))
        else:
            with args.answer_file.open(encoding="utf-8") as handle:
                _print_json(score_answer(args.case_id, json.load(handle)))
    except (BenchmarkError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
