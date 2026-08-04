import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref, validate_probability


def _node_status(topic: str, ref: str):
    kind, rid = parse_node_ref(ref)
    key = "facts" if kind == "fact" else "deductions"
    rec = next((r for r in storage.load_json_list(topic, key) if r["id"] == rid), None)
    return rec["status"] if rec else None


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--from", required=True, dest="from_node")
    p.add_argument("--to", required=True, dest="to_node")
    p.add_argument("--relation-type", required=True, dest="relation_type")
    p.add_argument("--prior", required=True, type=float)


def run(args):
    with topic_lock(args.topic):
        storage.prepare(args.topic)
        for ref in (args.from_node, args.to_node):
            status = _node_status(args.topic, ref)
            if status is None:
                raise ValidationError(f"unknown node reference: {ref}")
            if status != "active":
                raise ValidationError(
                    f"node reference {ref} is not active (status={status}); "
                    "cannot build a new edge on an inactive node"
                )
        prior = validate_probability(args.prior, "prior")
        record = {
            "id": new_id("edge"),
            "from_node": args.from_node,
            "to_node": args.to_node,
            "relation_type": args.relation_type,
            "prior": prior,
            "posterior": prior,
            "status": "active",
            "supersedes_id": None,
            "updates": [],
            "falsification_checks": [],
            "last_updated": time.time(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "propose-causal-edge", vars(args),
            [("causal_edges", record)],
        )
    print(record["id"])
