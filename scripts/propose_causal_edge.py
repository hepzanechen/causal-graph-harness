#!/usr/bin/env python3
import argparse
import sys
import time
from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref, validate_probability


def _node_exists(topic: str, ref: str) -> bool:
    kind, rid = parse_node_ref(ref)
    key = "facts" if kind == "fact" else "deductions"
    return any(r["id"] == rid for r in storage.load_json_list(topic, key))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--from", required=True, dest="from_node")
    p.add_argument("--to", required=True, dest="to_node")
    p.add_argument("--relation-type", required=True, dest="relation_type")
    p.add_argument("--prior", required=True, type=float)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        for ref in (args.from_node, args.to_node):
            if not _node_exists(args.topic, ref):
                raise ValidationError(f"unknown node reference: {ref}")
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
            args.topic, current_agent_id(), "propose_causal_edge.py", vars(args),
            [("causal_edges", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
