"""Public evidence broker and sealed evaluator for paired-30."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "cases.json"
GOLD_PATH = ROOT / "gold.json"
TRACE_PATH = ROOT / "evidence_trace.jsonl"
ID_RE = re.compile(r"^c[0-9]{2}$")


class BenchmarkError(ValueError):
    pass


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _cases() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in _read_json(CASES_PATH)}


def _case(case_id: str) -> dict[str, Any]:
    if not ID_RE.fullmatch(case_id):
        raise BenchmarkError(f"invalid case ID: {case_id!r}")
    try:
        return _cases()[case_id]
    except KeyError as exc:
        raise BenchmarkError(f"unknown case: {case_id}") from exc


def _normalize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _trace(action: str, case_id: str, evidence_ids: list[str], query: str | None = None) -> None:
    record = {"action": action, "case_id": case_id, "evidence_ids": evidence_ids}
    if query is not None:
        record["query"] = query
    with TRACE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def list_cases() -> list[dict[str, Any]]:
    return [
        {key: case[key] for key in ("id", "title", "difficulty", "source_types")}
        for case in _cases().values()
    ]


def load_case(case_id: str) -> dict[str, Any]:
    case = _case(case_id)
    return {key: case[key] for key in (
        "id", "title", "difficulty", "prompt", "source_types", "answer_contract",
    )}


def search_evidence(case_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    terms = set(_normalize(query))
    if not terms:
        raise BenchmarkError("query must contain at least one letter or digit")
    if not 1 <= limit <= 8:
        raise BenchmarkError("limit must be between 1 and 8")
    matches = []
    for item in _case(case_id)["evidence"]:
        searchable = set(_normalize(" ".join([
            item["component"], item["summary"], item["content"], " ".join(item["tags"]),
        ])))
        score = len(terms & searchable)
        if score:
            matches.append((score, item))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    selected = [item for _, item in matches[:limit]]
    _trace("search", case_id, [item["id"] for item in selected], query)
    return [{
        "id": item["id"],
        "source_type": item["source_type"],
        "component": item["component"],
        "timestamp": item["timestamp"],
        "summary": item["summary"],
        "excerpt": item["content"][:240],
    } for item in selected]


def read_evidence(case_id: str, evidence_id: str) -> dict[str, Any]:
    for item in _case(case_id)["evidence"]:
        if item["id"] == evidence_id:
            _trace("read", case_id, [evidence_id])
            return dict(item)
    raise BenchmarkError(f"unknown evidence ID for {case_id}: {evidence_id}")


def _id_list(answer: dict[str, Any], field: str) -> list[str]:
    value = answer.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BenchmarkError(f"{field} must be a list of strings")
    return value


def _f1(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _path_score(predicted: list[str], required: list[str], accepted: set[str]) -> dict[str, float | bool]:
    positions = {event_id: index for index, event_id in enumerate(predicted)}
    covered = [event_id for event_id in required if event_id in positions]
    ordered = all(positions[left] < positions[right] for left, right in zip(covered, covered[1:]))
    precision = sum(event_id in accepted for event_id in predicted) / len(predicted) if predicted else 0.0
    recall = len(covered) / len(required)
    return {"precision": precision, "recall": recall, "ordered": ordered}


def score_answer(case_id: str, answer: dict[str, Any]) -> dict[str, Any]:
    gold = _read_json(GOLD_PATH)[case_id]
    known = {item["id"] for item in _case(case_id)["evidence"]}
    roots = set(_id_list(answer, "root_event_ids"))
    supporting = set(_id_list(answer, "supporting_evidence_ids"))
    counter = set(_id_list(answer, "counterevidence_ids"))
    rejected = set(_id_list(answer, "rejected_distractor_ids"))
    raw_paths = answer.get("causal_paths")
    if not isinstance(raw_paths, list) or not raw_paths or not all(
        isinstance(path, list) and all(isinstance(item, str) for item in path)
        for path in raw_paths
    ):
        raise BenchmarkError("causal_paths must be a non-empty list of evidence-ID lists")

    all_reported = roots | supporting | counter | rejected | {
        item for path in raw_paths for item in path
    }
    unknown = sorted(all_reported - known)
    root_p, root_r, root_f1 = _f1(roots, set(gold["root_event_ids"]))
    accepted = set(gold["accepted_causal_event_ids"])
    path_scores = []
    for required in gold["required_paths"]:
        candidates = [_path_score(path, required, accepted) for path in raw_paths]
        path_scores.append(max(candidates, key=lambda score: (score["recall"], score["precision"])))
    chain_precision = sum(float(score["precision"]) for score in path_scores) / len(path_scores)
    chain_recall = sum(float(score["recall"]) for score in path_scores) / len(path_scores)
    chain_ordered = all(bool(score["ordered"]) for score in path_scores)
    chain_f1 = 2 * chain_precision * chain_recall / (chain_precision + chain_recall) if chain_precision + chain_recall else 0.0
    critical = set(gold["critical_supporting_evidence_ids"])
    accepted_support = set(gold["accepted_supporting_evidence_ids"])
    falsifying = set(gold["falsifying_evidence_ids"])
    distractors = set(gold["distractor_evidence_ids"])
    evidence_p = len(supporting & accepted_support) / len(supporting) if supporting else 0.0
    evidence_r = len(supporting & critical) / len(critical)
    evidence_f1 = 2 * evidence_p * evidence_r / (evidence_p + evidence_r) if evidence_p + evidence_r else 0.0
    _, falsifier_recall, _ = _f1(counter, falsifying)
    _, rejection_recall, _ = _f1(rejected, distractors)
    distractor_adoption = len((roots | {item for path in raw_paths for item in path}) & distractors) / len(distractors)
    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise BenchmarkError("confidence must be a number between 0 and 1")
    joint = (
        root_f1 == 1.0 and chain_precision == 1.0 and chain_recall == 1.0 and chain_ordered
        and distractor_adoption == 0.0 and not unknown
    )
    return {
        "case_id": case_id,
        "root_precision": round(root_p, 4),
        "root_recall": round(root_r, 4),
        "root_f1": round(root_f1, 4),
        "chain_precision": round(chain_precision, 4),
        "chain_recall": round(chain_recall, 4),
        "chain_f1": round(chain_f1, 4),
        "chain_ordered": chain_ordered,
        "critical_evidence_precision": round(evidence_p, 4),
        "critical_evidence_recall": round(evidence_r, 4),
        "critical_evidence_f1": round(evidence_f1, 4),
        "falsifying_evidence_recall": round(falsifier_recall, 4),
        "distractor_rejection_recall": round(rejection_recall, 4),
        "distractor_adoption_rate": round(distractor_adoption, 4),
        "unknown_evidence_ids": unknown,
        "joint_success": joint,
        "brier_joint_success": round((float(confidence) - float(joint)) ** 2, 4),
    }


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    prompt = commands.add_parser("prompt")
    prompt.add_argument("case_id")
    search = commands.add_parser("search")
    search.add_argument("case_id")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    read = commands.add_parser("read")
    read.add_argument("case_id")
    read.add_argument("evidence_id")
    score = commands.add_parser("score")
    score.add_argument("case_id")
    score.add_argument("answer_file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "list":
            _print(list_cases())
        elif args.command == "prompt":
            _print(load_case(args.case_id))
        elif args.command == "search":
            _print(search_evidence(args.case_id, args.query, args.limit))
        elif args.command == "read":
            _print(read_evidence(args.case_id, args.evidence_id))
        else:
            _print(score_answer(args.case_id, _read_json(args.answer_file)))
    except (BenchmarkError, OSError, json.JSONDecodeError, KeyError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
