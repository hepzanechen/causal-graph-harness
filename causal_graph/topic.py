import re
from pathlib import Path

from .schema import ValidationError

FILES = {
    "facts": "facts.json",
    "evidence": "evidence.json",
    "deductions": "deductions.json",
    "causal_edges": "causal_edges.json",
    "audit_log": "audit_log.jsonl",
    "pending_review": "pending_review.jsonl",
    "meta": "_meta.json",
}

_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def graph_dir(topic: str) -> Path:
    if not _TOPIC_RE.match(topic):
        raise ValidationError(
            f"invalid topic slug: {topic!r} (expected letters, digits, '_' or '-' only)"
        )
    return Path("research") / topic / "graph"


def ensure_graph_dir(topic: str) -> Path:
    d = graph_dir(topic)
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(topic: str, key: str) -> Path:
    return graph_dir(topic) / FILES[key]
