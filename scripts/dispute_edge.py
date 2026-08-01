#!/usr/bin/env python3
import argparse
import sys
from causal_graph import lifecycle, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                    choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")

        edge["status"] = args.new_status
        writes = [("causal_edges", edge)]
        writes += lifecycle.propagate_stale(args.topic, f"edge:{edge['id']}")

        storage.commit_mutation(
            args.topic, current_agent_id(), "dispute_edge.py", vars(args), writes,
        )
        print(edge["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
