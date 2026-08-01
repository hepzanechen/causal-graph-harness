from .schema import parse_node_ref


def _load_maps(topic: str):
    from . import storage
    facts = {f["id"]: f for f in storage.load_json_list(topic, "facts")}
    deductions = {d["id"]: d for d in storage.load_json_list(topic, "deductions")}
    edges = storage.load_json_list(topic, "causal_edges")
    return facts, deductions, edges


def downstream_dependents(topic: str, node_ref: str) -> set:
    facts, deductions, edges = _load_maps(topic)
    parse_node_ref(node_ref)  # validates format, raises ValidationError if malformed
    dependents: set = set()
    frontier = {node_ref}
    changed = True
    while changed:
        changed = False
        known = frontier | dependents
        for d in deductions.values():
            dref = f"deduction:{d['id']}"
            if dref in dependents:
                continue
            supports = {f"fact:{i}" for i in d.get("supporting_fact_ids", [])} | \
                       {f"deduction:{i}" for i in d.get("supporting_deduction_ids", [])}
            if supports & known:
                dependents.add(dref)
                frontier.add(dref)
                changed = True
        known = frontier | dependents
        for e in edges:
            eref = f"edge:{e['id']}"
            if eref in dependents:
                continue
            if e["from_node"] in known:
                dependents.add(eref)
                frontier.add(eref)
                changed = True
    return dependents


def urgency_tier(topic: str, node_ref: str) -> str:
    facts, deductions, edges = _load_maps(topic)
    total_nodes = len(facts) + len(deductions)
    if total_nodes < 8:
        return "normal"
    all_refs = [f"fact:{i}" for i in facts] + [f"deduction:{i}" for i in deductions]
    counts = sorted(len(downstream_dependents(topic, r)) for r in all_refs)
    my_count = len(downstream_dependents(topic, node_ref))
    rank = sum(1 for c in counts if c <= my_count) / len(counts)
    return "urgent" if rank >= 0.9 else "normal"
