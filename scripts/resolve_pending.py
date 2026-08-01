#!/usr/bin/env python3
import argparse
import sys
import time
from causal_graph import bayes, lifecycle, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--id", required=True, dest="item_id")
    p.add_argument("--action", required=True, choices=["approve", "reject", "amend"])
    p.add_argument("--amended-likelihood-ratio", type=float, default=None, dest="amended_likelihood_ratio")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        item = next((i for i in items if i["id"] == args.item_id), None)
        if item is None:
            raise ValidationError(f"unknown pending review id: {args.item_id}")

        writes = [("pending_review", {"id": args.item_id, "_delete": True})]

        if args.action != "reject":
            if item["kind"] == "causal_edge_update":
                edges = storage.load_json_list(args.topic, "causal_edges")
                edge = next(e for e in edges if e["id"] == item["edge_id"])
                update = dict(item["proposed_update"])
                if args.action == "amend":
                    if args.amended_likelihood_ratio is None:
                        raise ValidationError("--amended-likelihood-ratio required for amend")
                    update["likelihood_ratio"] = args.amended_likelihood_ratio
                edge["updates"] = edge["updates"] + [update]
                edge["posterior"] = bayes.compute_posterior(edge["prior"], edge["updates"])
                edge["last_updated"] = time.time()
                writes.append(("causal_edges", edge))
            elif item["kind"] == "fact_revision":
                facts = storage.load_json_list(args.topic, "facts")
                fact = next(f for f in facts if f["id"] == item["fact_id"])
                fact["status"] = item["new_status"]
                writes.append(("facts", fact))
                writes += lifecycle.propagate_stale(args.topic, f"fact:{fact['id']}")

        storage.commit_mutation(
            args.topic, current_agent_id(), "resolve_pending.py", vars(args), writes,
        )
    print(f"resolved {args.item_id}: {args.action}")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
