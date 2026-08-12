import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--alternative-hypothesis", required=True, dest="alternative_hypothesis")
    p.add_argument("--counterevidence-search", required=True, dest="counterevidence_search")
    p.add_argument("--result", required=True)


def run(args):
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
            args.topic, current_agent_id(), "record-falsification-check", vars(args),
            [("causal_edges", edge)],
        )
    print(edge["id"])
