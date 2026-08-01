#!/usr/bin/env python3
import argparse
import sys
import time
from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--alternative-hypothesis", required=True, dest="alternative_hypothesis")
    p.add_argument("--counterevidence-search", required=True, dest="counterevidence_search")
    p.add_argument("--result", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")
        edge["falsification_checks"].append({
            "alternative_hypothesis": args.alternative_hypothesis,
            "counterevidence_search_result": f"{args.counterevidence_search} -> {args.result}",
            "checked_by": current_agent_id(),
            "checked_at": time.time(),
        })
        storage.commit_mutation(
            args.topic, current_agent_id(), "record_falsification_check.py", vars(args),
            [("causal_edges", edge)],
        )
    print(edge["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
