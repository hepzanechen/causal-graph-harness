#!/usr/bin/env python3
import argparse
import sys
import time
from causal_graph import lifecycle, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--fact-id", required=True, dest="fact_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                    choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)
    p.add_argument("--replacement-statement", default=None, dest="replacement_statement")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        facts = storage.load_json_list(args.topic, "facts")
        fact = next((f for f in facts if f["id"] == args.fact_id), None)
        if fact is None:
            raise ValidationError(f"unknown fact id: {args.fact_id}")

        agent_id = current_agent_id()
        if fact["confidence"] == "verified" and agent_id != "human":
            item = {
                "id": new_id("rev"),
                "kind": "fact_revision",
                "fact_id": fact["id"],
                "new_status": args.new_status,
                "reason": args.reason,
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, agent_id, "revise_fact.py", vars(args),
                [("pending_review", item)],
            )
            print(f"queued for review: {item['id']} (agent attempted to revise a human-verified fact)")
            return

        fact["status"] = args.new_status
        writes = [("facts", fact)]
        writes += lifecycle.propagate_stale(args.topic, f"fact:{fact['id']}")

        if args.replacement_statement:
            new_fact = dict(fact)
            new_fact["id"] = new_id("fact")
            new_fact["statement"] = args.replacement_statement
            new_fact["status"] = "active"
            new_fact["supersedes_id"] = fact["id"]
            new_fact["created_at"] = time.time()
            new_fact["created_by"] = agent_id
            writes.append(("facts", new_fact))

        storage.commit_mutation(
            args.topic, agent_id, "revise_fact.py", vars(args), writes,
        )
        print(fact["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
