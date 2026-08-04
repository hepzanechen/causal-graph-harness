from causal_graph import lifecycle, storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                   choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)


def run(args):
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
            args.topic, current_agent_id(), "dispute-edge", vars(args), writes,
        )
        print(edge["id"])
