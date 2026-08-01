from pathlib import Path

FILES = {
    "facts": "facts.json",
    "evidence": "evidence.json",
    "deductions": "deductions.json",
    "causal_edges": "causal_edges.json",
    "audit_log": "audit_log.jsonl",
    "pending_review": "pending_review.jsonl",
    "meta": "_meta.json",
}


def graph_dir(topic: str) -> Path:
    return Path("research") / topic / "graph"


def ensure_graph_dir(topic: str) -> Path:
    d = graph_dir(topic)
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(topic: str, key: str) -> Path:
    return graph_dir(topic) / FILES[key]
