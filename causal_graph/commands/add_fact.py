import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import Confidence, ValidationError, new_id


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--statement", required=True)
    p.add_argument("--evidence-id", action="append", required=True, dest="evidence_ids")
    p.add_argument("--confidence", required=True, choices=[c.value for c in Confidence])
    p.add_argument("--contradicts", default=None, help="ID of an existing fact this contradicts")


def run(args):
    with topic_lock(args.topic):
        storage.prepare(args.topic)
        known_evidence = {e["id"] for e in storage.load_json_list(args.topic, "evidence")}
        missing = [eid for eid in args.evidence_ids if eid not in known_evidence]
        if missing:
            raise ValidationError(f"unknown evidence id(s): {missing}")

        candidate = {
            "id": new_id("fact"),
            "statement": args.statement,
            "evidence_ids": args.evidence_ids,
            "confidence": args.confidence,
            "status": "active",
            "supersedes_id": None,
            "created_at": time.time(),
            "created_by": current_agent_id(),
        }

        if args.contradicts:
            known_facts = {f["id"] for f in storage.load_json_list(args.topic, "facts")}
            if args.contradicts not in known_facts:
                raise ValidationError(f"unknown contradicts target: {args.contradicts}")
            item = {
                "id": new_id("rev"),
                "kind": "contradiction",
                "candidate_fact": candidate,
                "contradicts_fact_id": args.contradicts,
                "reason": f"flagged as contradicting {args.contradicts}",
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, current_agent_id(), "add-fact", vars(args),
                [("pending_review", item)],
            )
            print(f"queued for review: {item['id']} (candidate fact {candidate['id']} contradicts {args.contradicts})")
            return

        storage.commit_mutation(
            args.topic, current_agent_id(), "add-fact", vars(args), [("facts", candidate)],
        )
    print(candidate["id"])
