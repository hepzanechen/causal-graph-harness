#!/usr/bin/env python3
import argparse
import sys
import time

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--source-ref", required=True, dest="source_ref")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        record = {
            "id": new_id("ev"),
            "content": args.content,
            "source_adapter": args.adapter,
            "source_ref": args.source_ref,
            "retrieved_at": time.time(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "add_evidence.py", vars(args),
            [("evidence", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
