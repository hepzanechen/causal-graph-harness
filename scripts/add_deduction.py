#!/usr/bin/env python3
import argparse
import sys
import time
from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--supports", required=True, help="comma-separated fact:ID/deduction:ID refs")
    p.add_argument("--logic-note", default="", dest="logic_note")
    args = p.parse_args()

    refs = [r.strip() for r in args.supports.split(",") if r.strip()]
    fact_ids, deduction_ids = [], []
    for r in refs:
        kind, rid = parse_node_ref(r)
        (fact_ids if kind == "fact" else deduction_ids).append(rid)

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        known_facts = {f["id"] for f in storage.load_json_list(args.topic, "facts")}
        known_deductions = {d["id"] for d in storage.load_json_list(args.topic, "deductions")}
        missing = [f"fact:{i}" for i in fact_ids if i not in known_facts] + \
                  [f"deduction:{i}" for i in deduction_ids if i not in known_deductions]
        if missing:
            raise ValidationError(f"unknown supporting node(s): {missing}")

        record = {
            "id": new_id("ded"),
            "claim": args.claim,
            "supporting_fact_ids": fact_ids,
            "supporting_deduction_ids": deduction_ids,
            "logic_note": args.logic_note,
            "status": "active",
            "supersedes_id": None,
            "created_at": time.time(),
            "created_by": current_agent_id(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "add_deduction.py", vars(args),
            [("deductions", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
