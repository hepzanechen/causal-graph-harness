from . import storage
from .graph import downstream_dependents

_KEY_BY_KIND = {"deduction": "deductions", "edge": "causal_edges"}


def propagate_stale(topic: str, node_ref: str) -> list:
    kind = node_ref.split(":", 1)[0]
    if kind == "edge":
        return []  # causal edges have no downstream dependents in this graph model

    dependents = downstream_dependents(topic, node_ref)
    writes = []
    for ref in dependents:
        dep_kind, rid = ref.split(":", 1)
        key = _KEY_BY_KIND.get(dep_kind)
        if key is None:
            continue
        records = storage.load_json_list(topic, key)
        rec = next((r for r in records if r["id"] == rid), None)
        if rec is not None and rec.get("status") == "active":
            rec["status"] = "stale"
            writes.append((key, rec))
    return writes
