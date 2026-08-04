import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import new_id


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--source-ref", required=True, dest="source_ref")


def run(args):
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
            args.topic, current_agent_id(), "add-evidence", vars(args),
            [("evidence", record)],
        )
    print(record["id"])
