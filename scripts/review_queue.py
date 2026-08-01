#!/usr/bin/env python3
import argparse
import json
import sys
from causal_graph import graph as graphmod
from causal_graph import storage
from causal_graph.lock import topic_lock


def _base_ref_for(item: dict, topic: str):
    if item["kind"] == "causal_edge_update":
        edges = storage.load_json_list(topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == item["edge_id"]), None)
        return edge["to_node"] if edge else None
    if item["kind"] in ("fact_revision", "contradiction"):
        return f"fact:{item['fact_id']}"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        for item in items:
            ref = _base_ref_for(item, args.topic)
            item["tier"] = graphmod.urgency_tier(args.topic, ref) if ref else "normal"
    print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
