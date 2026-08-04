import time

from causal_graph import bayes, review, storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, validate_likelihood_ratio


def _needs_review(edge: dict, new_posterior: float):
    if review.crosses_high_confidence(edge["posterior"], new_posterior) and not edge["falsification_checks"]:
        return True, "high-confidence threshold crossed without a recorded falsification check"
    if review.is_reversal(edge["prior"], edge["posterior"], new_posterior):
        return True, "evidence reverses the edge's trend beyond the configured margin"
    return False, None


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--evidence-id", required=True, dest="evidence_id")
    p.add_argument("--likelihood-ratio", required=True, type=float, dest="likelihood_ratio")
    p.add_argument("--correlated-with", default="", dest="correlated_with")


def run(args):
    correlated_with = [c.strip() for c in args.correlated_with.split(",") if c.strip()]
    lr = validate_likelihood_ratio(args.likelihood_ratio)

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")
        if edge["status"] in ("retracted", "superseded"):
            raise ValidationError(
                f"edge {edge['id']} is {edge['status']}; cannot apply new updates to it"
            )
        known_evidence = {e["id"] for e in storage.load_json_list(args.topic, "evidence")}
        if args.evidence_id not in known_evidence:
            raise ValidationError(f"unknown evidence id: {args.evidence_id}")

        applied_evidence_ids = {u["evidence_id"] for u in edge["updates"]}
        if args.evidence_id in applied_evidence_ids:
            raise ValidationError(
                f"evidence {args.evidence_id} has already been applied to edge {edge['id']}"
            )
        unknown_correlated = [c for c in correlated_with if c not in applied_evidence_ids]
        if unknown_correlated:
            raise ValidationError(
                f"--correlated-with references evidence not yet applied to this edge: {unknown_correlated}"
            )

        new_update = {
            "evidence_id": args.evidence_id,
            "likelihood_ratio": lr,
            "correlated_with": correlated_with,
            "agent": current_agent_id(),
            "timestamp": time.time(),
        }
        trial_updates = edge["updates"] + [new_update]
        new_posterior = bayes.compute_posterior(edge["prior"], trial_updates)

        needs_review, reason = _needs_review(edge, new_posterior)
        if needs_review:
            item = {
                "id": new_id("rev"),
                "kind": "causal_edge_update",
                "edge_id": edge["id"],
                "proposed_update": new_update,
                "proposed_posterior": new_posterior,
                "reason": reason,
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, current_agent_id(), "update-causal-edge", vars(args),
                [("pending_review", item)],
            )
            print(f"queued for review: {item['id']} ({reason})")
            return

        edge["updates"] = trial_updates
        edge["posterior"] = new_posterior
        if edge["status"] == "stale":
            # Explicit reaffirmation: successfully re-running the normal
            # update path against a stale edge brings it back into the
            # current view, per the lifecycle-propagation contract.
            edge["status"] = "active"
        edge["last_updated"] = time.time()
        storage.commit_mutation(
            args.topic, current_agent_id(), "update-causal-edge", vars(args),
            [("causal_edges", edge)],
        )
        print(edge["id"])
