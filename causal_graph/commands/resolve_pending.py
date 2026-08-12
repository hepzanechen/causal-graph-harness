import time

from causal_graph import bayes, lifecycle, storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, validate_likelihood_ratio


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--id", required=True, dest="item_id")
    p.add_argument("--action", required=True, choices=["approve", "reject", "amend"])
    p.add_argument("--amended-likelihood-ratio", type=float, default=None, dest="amended_likelihood_ratio")


def run(args):
    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        item = next((i for i in items if i["id"] == args.item_id), None)
        if item is None:
            raise ValidationError(f"unknown pending review id: {args.item_id}")

        if args.action == "amend" and item["kind"] != "causal_edge_update":
            raise ValidationError(f"amend is not supported for pending items of kind {item['kind']!r}")

        writes = [("pending_review", {"id": args.item_id, "_delete": True})]

        if args.action != "reject":
            if item["kind"] == "causal_edge_update":
                edges = storage.load_json_list(args.topic, "causal_edges")
                edge = next((e for e in edges if e["id"] == item["edge_id"]), None)
                if edge is None:
                    raise ValidationError(f"unknown edge id: {item['edge_id']}")
                if edge["status"] in ("retracted", "superseded"):
                    raise ValidationError(
                        f"edge {edge['id']} is {edge['status']}; this pending item is stale"
                    )
                update = dict(item["proposed_update"])
                if args.action == "amend":
                    if args.amended_likelihood_ratio is None:
                        raise ValidationError("--amended-likelihood-ratio required for amend")
                    update["likelihood_ratio"] = validate_likelihood_ratio(args.amended_likelihood_ratio)
                already_applied = {u["evidence_id"] for u in edge["updates"]}
                if update["evidence_id"] in already_applied:
                    raise ValidationError(
                        f"evidence {update['evidence_id']} has already been applied to edge "
                        f"{edge['id']}; this pending item is stale"
                    )
                edge["updates"] = edge["updates"] + [update]
                edge["posterior"] = bayes.compute_posterior(edge["prior"], edge["updates"])
                if edge["status"] == "stale":
                    edge["status"] = "active"
                edge["last_updated"] = time.time()
                writes.append(("causal_edges", edge))
            elif item["kind"] == "fact_revision":
                facts = storage.load_json_list(args.topic, "facts")
                fact = next((f for f in facts if f["id"] == item["fact_id"]), None)
                if fact is None:
                    raise ValidationError(f"unknown fact id: {item['fact_id']}")
                fact["status"] = item["new_status"]
                writes.append(("facts", fact))
                writes += lifecycle.propagate_stale(args.topic, f"fact:{fact['id']}")
                if item.get("replacement_statement"):
                    new_fact = dict(fact)
                    new_fact["id"] = new_id("fact")
                    new_fact["statement"] = item["replacement_statement"]
                    new_fact["status"] = "active"
                    new_fact["supersedes_id"] = fact["id"]
                    new_fact["created_at"] = time.time()
                    new_fact["created_by"] = current_agent_id()
                    writes.append(("facts", new_fact))
            elif item["kind"] == "contradiction":
                facts = storage.load_json_list(args.topic, "facts")
                old_fact = next((f for f in facts if f["id"] == item["contradicts_fact_id"]), None)
                if old_fact is None:
                    raise ValidationError(f"unknown fact id: {item['contradicts_fact_id']}")
                if old_fact["status"] != "active":
                    raise ValidationError(
                        f"fact {old_fact['id']} is {old_fact['status']}, not active; "
                        "this pending item is stale"
                    )
                new_fact = dict(item["candidate_fact"])
                new_fact["supersedes_id"] = item["contradicts_fact_id"]
                writes.append(("facts", new_fact))
                old_fact["status"] = "superseded"
                writes.append(("facts", old_fact))
                writes += lifecycle.propagate_stale(args.topic, f"fact:{old_fact['id']}")

        storage.commit_mutation(
            args.topic, current_agent_id(), "resolve-pending", vars(args), writes,
        )
    print(f"resolved {args.item_id}: {args.action}")
