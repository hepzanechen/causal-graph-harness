# Cross-Agent Plugin Manifests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repo-relative `python scripts/<name>.py` scripts with one installed, cwd-independent `causal-graph` CLI, then add per-agent plugin manifests (Claude Code, Codex, Cursor) that point at a single shared skill doc — implementing item 1 of the parent spec's deferred "Future work: cross-agent distribution" section.

**Architecture:** Ten command modules under `causal_graph/commands/`, each exposing `add_arguments(parser)` + `run(args)` (logic unchanged from today's scripts, just relocated). `causal_graph/cli.py` owns one `argparse` dispatcher wiring all ten as subcommands of `causal-graph`, registered via `pyproject.toml`'s `[project.scripts]` so `pip install -e .` puts it on `PATH` regardless of cwd. `scripts/*.py` and the old subprocess-based test helpers are then deleted in favor of a shared `tests/cli_support.py`. Three JSON plugin manifests point every agent at one canonical `skills/causal-graph-research/SKILL.md`.

**Tech Stack:** Python >= 3.10 stdlib only (argparse, json, fcntl), pytest for tests, setuptools for packaging. No new runtime dependencies.

## Global Constraints

- No third-party runtime dependencies (`pytest` stays dev-only) — per `AGENTS.md`.
- Every script's existing flags, exit codes, and stdout/stderr contract (`error: ...` on stderr + exit 1, printed ID or `queued for review: ...` on stdout + exit 0) must be preserved exactly — this is a relocation/packaging refactor, not a behavior change.
- `causal-graph <subcommand> --topic T` must resolve `research/T/graph/` relative to the caller's cwd, same as today — installing the command doesn't change where data lives.
- Repository is a public GitHub repo at `git@github.com:hepzanechen/causal-graph-harness.git`; manifests reference `https://github.com/hepzanechen/causal-graph-harness`.
- Design source of truth: `docs/superpowers/specs/2026-08-05-cross-agent-plugin-manifests-design.md`.

---

### Task 1: `causal_graph/agent.py` + graph-building commands (add-evidence, add-fact, add-deduction, propose-causal-edge)

**Files:**
- Create: `causal_graph/agent.py`
- Create: `causal_graph/commands/__init__.py`
- Create: `causal_graph/commands/add_evidence.py`
- Create: `causal_graph/commands/add_fact.py`
- Create: `causal_graph/commands/add_deduction.py`
- Create: `causal_graph/commands/propose_causal_edge.py`
- Modify: `causal_graph/cli.py`
- Modify: `pyproject.toml`
- Test: manual smoke test in this task (automated `--help`/help-text tests come in Task 4 once all subcommands exist)

**Interfaces:**
- Produces: each `causal_graph/commands/<name>.py` exposes `add_arguments(parser: argparse.ArgumentParser) -> None` (registers that subcommand's flags) and `run(args: argparse.Namespace) -> None` (does the work, prints the result, raises `causal_graph.schema.ValidationError` on invalid input — same contract as today's `main()` bodies).
- Produces: `causal_graph.agent.current_agent_id() -> str` (moved out of `cli.py` to avoid a `cli` ↔ `commands` circular import; `cli.py` re-exports it so `tests/test_sanity.py`'s existing `from causal_graph.cli import current_agent_id` keeps working unchanged).
- Consumes: `causal_graph.storage`, `causal_graph.lock.topic_lock`, `causal_graph.schema` (all already exist, untouched).

- [ ] **Step 1: Create `causal_graph/agent.py`**

```python
import os


def current_agent_id() -> str:
    return os.environ.get("CAUSAL_GRAPH_AGENT_ID", "agent")
```

- [ ] **Step 2: Create `causal_graph/commands/__init__.py`** (empty file, marks the package)

- [ ] **Step 3: Create `causal_graph/commands/add_evidence.py`**

```python
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
```

- [ ] **Step 4: Create `causal_graph/commands/add_fact.py`**

```python
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
```

- [ ] **Step 5: Create `causal_graph/commands/add_deduction.py`**

```python
import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--supports", required=True, help="comma-separated fact:ID/deduction:ID refs")
    p.add_argument("--logic-note", default="", dest="logic_note")


def run(args):
    refs = [r.strip() for r in args.supports.split(",") if r.strip()]
    if not refs:
        raise ValidationError("--supports must reference at least one fact or deduction")
    fact_ids, deduction_ids = [], []
    for r in refs:
        kind, rid = parse_node_ref(r)
        (fact_ids if kind == "fact" else deduction_ids).append(rid)

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        known_facts = {f["id"]: f for f in storage.load_json_list(args.topic, "facts")}
        known_deductions = {d["id"]: d for d in storage.load_json_list(args.topic, "deductions")}
        missing = [f"fact:{i}" for i in fact_ids if i not in known_facts] + \
                  [f"deduction:{i}" for i in deduction_ids if i not in known_deductions]
        if missing:
            raise ValidationError(f"unknown supporting node(s): {missing}")
        inactive = [f"fact:{i}" for i in fact_ids if known_facts[i]["status"] != "active"] + \
                   [f"deduction:{i}" for i in deduction_ids if known_deductions[i]["status"] != "active"]
        if inactive:
            raise ValidationError(f"supporting node(s) not active: {inactive}")

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
            args.topic, current_agent_id(), "add-deduction", vars(args),
            [("deductions", record)],
        )
    print(record["id"])
```

- [ ] **Step 6: Create `causal_graph/commands/propose_causal_edge.py`**

```python
import time

from causal_graph import storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref, validate_probability


def _node_status(topic: str, ref: str):
    kind, rid = parse_node_ref(ref)
    key = "facts" if kind == "fact" else "deductions"
    rec = next((r for r in storage.load_json_list(topic, key) if r["id"] == rid), None)
    return rec["status"] if rec else None


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--from", required=True, dest="from_node")
    p.add_argument("--to", required=True, dest="to_node")
    p.add_argument("--relation-type", required=True, dest="relation_type")
    p.add_argument("--prior", required=True, type=float)


def run(args):
    with topic_lock(args.topic):
        storage.prepare(args.topic)
        for ref in (args.from_node, args.to_node):
            status = _node_status(args.topic, ref)
            if status is None:
                raise ValidationError(f"unknown node reference: {ref}")
            if status != "active":
                raise ValidationError(
                    f"node reference {ref} is not active (status={status}); "
                    "cannot build a new edge on an inactive node"
                )
        prior = validate_probability(args.prior, "prior")
        record = {
            "id": new_id("edge"),
            "from_node": args.from_node,
            "to_node": args.to_node,
            "relation_type": args.relation_type,
            "prior": prior,
            "posterior": prior,
            "status": "active",
            "supersedes_id": None,
            "updates": [],
            "falsification_checks": [],
            "last_updated": time.time(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "propose-causal-edge", vars(args),
            [("causal_edges", record)],
        )
    print(record["id"])
```

- [ ] **Step 7: Wire `causal_graph/cli.py`** — replace its entire current content (just `current_agent_id`) with the dispatcher, importing only the four modules that exist so far:

```python
import argparse
import sys

from .agent import current_agent_id  # noqa: F401 (re-exported for tests/test_sanity.py)
from .commands import add_evidence, add_fact, add_deduction, propose_causal_edge
from .schema import ValidationError

_COMMANDS = {
    "add-evidence": add_evidence,
    "add-fact": add_fact,
    "add-deduction": add_deduction,
    "propose-causal-edge": propose_causal_edge,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="causal-graph")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module in _COMMANDS.items():
        sub = subparsers.add_parser(name)
        module.add_arguments(sub)
    args = parser.parse_args(argv)
    module = _COMMANDS[args.command]
    try:
        module.run(args)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(Later tasks add more entries to `_COMMANDS` and their imports — nothing else in this file changes shape.)

- [ ] **Step 8: Update `pyproject.toml`** — add the console-script entry point and the new package:

```toml
[project.scripts]
causal-graph = "causal_graph.cli:main"

[tool.setuptools]
packages = ["causal_graph", "causal_graph.commands", "adapters"]
```

(Insert `[project.scripts]` as its own table anywhere after `[project]`; update the existing `[tool.setuptools]` table's `packages` line in place.)

- [ ] **Step 9: Reinstall and smoke-test**

```bash
pip install -e .
cd /tmp && rm -rf cg-smoke && mkdir cg-smoke && cd cg-smoke
ev=$(causal-graph add-evidence --topic t --adapter human --content "c" --source-ref "r")
echo "$ev"
fact=$(causal-graph add-fact --topic t --statement "A" --evidence-id "$ev" --confidence verified)
echo "$fact"
causal-graph add-deduction --topic t --claim "x" --supports "fact:$fact"
causal-graph propose-causal-edge --topic t --from "fact:$fact" --to "fact:$fact" --relation-type contributes-to --prior 0.3
cd /home/kt/zero
```

Expected: each command prints a non-empty ID, no tracebacks. `research/t/graph/facts.json` etc. appear under `/tmp/cg-smoke/research/t/graph/`. The old `scripts/*.py` still exist untouched and the existing test suite (which still targets them) still passes:

```bash
pytest -v
```

Expected: PASS (unchanged — this task is purely additive).

- [ ] **Step 10: Commit**

```bash
git add causal_graph/agent.py causal_graph/commands/ causal_graph/cli.py pyproject.toml
git commit -m "Add causal-graph CLI: agent module + graph-building subcommands

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: update/lifecycle commands (update-causal-edge, record-falsification-check, revise-fact, dispute-edge)

**Files:**
- Create: `causal_graph/commands/update_causal_edge.py`
- Create: `causal_graph/commands/record_falsification_check.py`
- Create: `causal_graph/commands/revise_fact.py`
- Create: `causal_graph/commands/dispute_edge.py`
- Modify: `causal_graph/cli.py`

**Interfaces:**
- Consumes: `causal_graph.bayes.compute_posterior`, `causal_graph.review.crosses_high_confidence`/`is_reversal`, `causal_graph.lifecycle.propagate_stale` (all pre-existing, untouched).
- Produces: same `add_arguments`/`run` contract as Task 1's modules.

- [ ] **Step 1: Create `causal_graph/commands/update_causal_edge.py`**

```python
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
```

- [ ] **Step 2: Create `causal_graph/commands/record_falsification_check.py`**

```python
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
```

- [ ] **Step 3: Create `causal_graph/commands/revise_fact.py`**

```python
import time

from causal_graph import lifecycle, storage
from causal_graph.agent import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id


def add_arguments(p):
    p.add_argument("--topic", required=True)
    p.add_argument("--fact-id", required=True, dest="fact_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                   choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)
    p.add_argument("--replacement-statement", default=None, dest="replacement_statement")


def run(args):
    if args.replacement_statement and args.new_status != "superseded":
        raise ValidationError("--replacement-statement requires --new-status superseded")

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
                "replacement_statement": args.replacement_statement,
                "reason": args.reason,
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, agent_id, "revise-fact", vars(args),
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
            args.topic, agent_id, "revise-fact", vars(args), writes,
        )
        print(fact["id"])
```

- [ ] **Step 4: Create `causal_graph/commands/dispute_edge.py`**

```python
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
```

- [ ] **Step 5: Update `causal_graph/cli.py`** — extend the imports and `_COMMANDS` dict:

```python
from .commands import (
    add_evidence, add_fact, add_deduction, propose_causal_edge,
    update_causal_edge, record_falsification_check, revise_fact, dispute_edge,
)

_COMMANDS = {
    "add-evidence": add_evidence,
    "add-fact": add_fact,
    "add-deduction": add_deduction,
    "propose-causal-edge": propose_causal_edge,
    "update-causal-edge": update_causal_edge,
    "record-falsification-check": record_falsification_check,
    "revise-fact": revise_fact,
    "dispute-edge": dispute_edge,
}
```

(Replace the Task 1 import line and `_COMMANDS` dict wholesale with the above — everything else in the file is unchanged.)

- [ ] **Step 6: Smoke-test and run full suite**

```bash
pip install -e .
cd /tmp/cg-smoke
ev=$(causal-graph add-evidence --topic t2 --adapter human --content c --source-ref r)
f1=$(causal-graph add-fact --topic t2 --statement A --evidence-id "$ev" --confidence verified)
f2=$(causal-graph add-fact --topic t2 --statement B --evidence-id "$ev" --confidence verified)
edge=$(causal-graph propose-causal-edge --topic t2 --from "fact:$f1" --to "fact:$f2" --relation-type contributes-to --prior 0.3)
causal-graph update-causal-edge --topic t2 --edge-id "$edge" --evidence-id "$ev" --likelihood-ratio 2.0
causal-graph record-falsification-check --topic t2 --edge-id "$edge" --alternative-hypothesis alt --counterevidence-search search --result "null result"
causal-graph dispute-edge --topic t2 --edge-id "$edge" --new-status contested --reason test
cd /home/kt/zero
pytest -v
```

Expected: all commands print an ID with no traceback; full suite (still targeting `scripts/`) PASSes unchanged.

- [ ] **Step 7: Commit**

```bash
git add causal_graph/commands/ causal_graph/cli.py
git commit -m "Add update/lifecycle subcommands to causal-graph CLI

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: review commands (review-queue, resolve-pending) + full dispatcher

**Files:**
- Create: `causal_graph/commands/review_queue.py`
- Create: `causal_graph/commands/resolve_pending.py`
- Modify: `causal_graph/cli.py`

**Interfaces:**
- Consumes: `causal_graph.graph.urgency_tier` (pre-existing, untouched).
- Produces: `_COMMANDS` now contains all ten subcommands — this is the dict later tasks' tests assert against.

- [ ] **Step 1: Create `causal_graph/commands/review_queue.py`**

```python
import json

from causal_graph import graph as graphmod
from causal_graph import storage
from causal_graph.lock import topic_lock


def _base_ref_for(item: dict, topic: str):
    if item["kind"] == "causal_edge_update":
        edges = storage.load_json_list(topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == item["edge_id"]), None)
        return edge["to_node"] if edge else None
    if item["kind"] in ("fact_revision", "contradiction"):
        return f"fact:{item['fact_id']}"
    return None


def add_arguments(p):
    p.add_argument("--topic", required=True)


def run(args):
    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        for item in items:
            ref = _base_ref_for(item, args.topic)
            item["tier"] = graphmod.urgency_tier(args.topic, ref) if ref else "normal"
    print(json.dumps(items, indent=2))
```

- [ ] **Step 2: Create `causal_graph/commands/resolve_pending.py`**

```python
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
```

- [ ] **Step 3: Update `causal_graph/cli.py`** to its final, complete form:

```python
import argparse
import sys

from .agent import current_agent_id  # noqa: F401 (re-exported for tests/test_sanity.py)
from .commands import (
    add_evidence, add_fact, add_deduction, propose_causal_edge,
    update_causal_edge, record_falsification_check, revise_fact, dispute_edge,
    review_queue, resolve_pending,
)
from .schema import ValidationError

_COMMANDS = {
    "add-evidence": add_evidence,
    "add-fact": add_fact,
    "add-deduction": add_deduction,
    "propose-causal-edge": propose_causal_edge,
    "update-causal-edge": update_causal_edge,
    "record-falsification-check": record_falsification_check,
    "revise-fact": revise_fact,
    "dispute-edge": dispute_edge,
    "review-queue": review_queue,
    "resolve-pending": resolve_pending,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="causal-graph")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module in _COMMANDS.items():
        sub = subparsers.add_parser(name)
        module.add_arguments(sub)
    args = parser.parse_args(argv)
    module = _COMMANDS[args.command]
    try:
        module.run(args)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Smoke-test and run full suite**

```bash
pip install -e .
causal-graph --help
causal-graph review-queue --topic t2
pytest -v
```

Expected: `--help` lists all ten subcommand names; `review-queue` prints `[]` (no pending items in `t2`... it does have none pending, only a dispute — confirm it runs without traceback regardless of contents); full suite still PASSes (unchanged, still targets `scripts/`).

- [ ] **Step 5: Commit**

```bash
git add causal_graph/commands/ causal_graph/cli.py
git commit -m "Complete causal-graph CLI dispatcher with review subcommands

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `--help` smoke tests for the installed CLI

**Files:**
- Create: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: the installed `causal-graph` console script (via `subprocess` + `sys.executable -m causal_graph.cli`, so it works even if `PATH` doesn't include the venv's script dir in the test runner) and the `_COMMANDS` dict names from `causal_graph.cli`.

- [ ] **Step 1: Write the test**

```python
import subprocess
import sys

from causal_graph.cli import _COMMANDS


def test_top_level_help_lists_all_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    for name in _COMMANDS:
        assert name in result.stdout


def test_subcommand_help_shows_its_flags():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "add-fact", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--statement" in result.stdout
    assert "--confidence" in result.stdout


def test_unknown_subcommand_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "not-a-command"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run it**

```bash
pytest tests/test_cli_help.py -v
```

Expected: all three PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_help.py
git commit -m "Add --help smoke tests for the causal-graph CLI dispatcher

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: shared `tests/cli_support.py` + migrate the four simple test files

**Files:**
- Create: `tests/cli_support.py`
- Modify: `tests/test_add_evidence.py`
- Modify: `tests/test_add_fact.py`
- Modify: `tests/test_add_deduction.py`
- Modify: `tests/test_propose_causal_edge.py`

**Interfaces:**
- Produces: `tests.cli_support.run_cli(script: str, args: list[str], cwd) -> subprocess.CompletedProcess` — same three-positional-argument shape every existing test file's `_run(script, args, cwd)` already uses, so only the helper import changes; the args lists and assertions in every test function are untouched.

- [ ] **Step 1: Create `tests/cli_support.py`**

```python
import subprocess
import sys

_SUBCOMMAND = {
    "add_evidence.py": "add-evidence",
    "add_fact.py": "add-fact",
    "add_deduction.py": "add-deduction",
    "propose_causal_edge.py": "propose-causal-edge",
    "update_causal_edge.py": "update-causal-edge",
    "record_falsification_check.py": "record-falsification-check",
    "revise_fact.py": "revise-fact",
    "dispute_edge.py": "dispute-edge",
    "review_queue.py": "review-queue",
    "resolve_pending.py": "resolve-pending",
}


def run_cli(script, args, cwd):
    """Invoke the causal-graph CLI's subcommand for `script` (its old
    scripts/<script> filename, kept as the lookup key so every test file's
    existing `_run("add_fact.py", [...], cwd=...)` call sites don't need to
    change — only each file's local `_run` definition does).
    """
    return subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", _SUBCOMMAND[script], *args],
        cwd=cwd, capture_output=True, text=True,
    )
```

- [ ] **Step 2: Rewrite `tests/test_add_evidence.py`** — replace the whole file (its `_run` takes no `script` arg today, unlike the others, so this file's `_run` call sites change to match the shared shape):

```python
from causal_graph import storage
from tests.cli_support import run_cli as _run


def test_add_evidence_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "saw it happen",
        "--source-ref", "conversation:2026-08-01",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    ev_id = result.stdout.strip()
    records = storage.load_json_list("t", "evidence")
    assert len(records) == 1
    assert records[0]["id"] == ev_id
    assert records[0]["source_adapter"] == "human"
    assert records[0]["content"] == "saw it happen"
```

- [ ] **Step 3: Edit `tests/test_add_fact.py`** — replace the top-of-file boilerplate and remove every `_copy_scripts(tmp_path)` call line (four occurrences, one per test function):

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

Then remove each of the four `    _copy_scripts(tmp_path)` lines (they appear directly after each `monkeypatch.chdir(tmp_path)`).

- [ ] **Step 4: Edit `tests/test_add_deduction.py`** — same pattern (replace the top-of-file block, remove the four `_copy_scripts(tmp_path)` call lines):

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py", "revise_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 5: Edit `tests/test_propose_causal_edge.py`** — same pattern (replace the top-of-file block, remove every `_copy_scripts(tmp_path)` call line):

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py",
                 "propose_causal_edge.py", "revise_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 6: Run the four files**

```bash
pytest tests/test_add_evidence.py tests/test_add_fact.py tests/test_add_deduction.py tests/test_propose_causal_edge.py -v
```

Expected: all PASS. (`scripts/*.py` still exist and are now unused by these four files, but Task 2/3's other test files still reference them — do not delete yet.)

- [ ] **Step 7: Commit**

```bash
git add tests/cli_support.py tests/test_add_evidence.py tests/test_add_fact.py tests/test_add_deduction.py tests/test_propose_causal_edge.py
git commit -m "Migrate simple CLI tests to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: migrate `tests/test_update_causal_edge.py`

**Files:**
- Modify: `tests/test_update_causal_edge.py`

**Interfaces:**
- Consumes: `tests.cli_support.run_cli` (Task 5).

- [ ] **Step 1: Replace the top-of-file block**

```python
old_string:
# tests/test_update_causal_edge.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py", "update_causal_edge.py",
           "revise_fact.py", "dispute_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
# tests/test_update_causal_edge.py
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 2: Remove every `_copy_scripts(tmp_path)` call line** — eight occurrences, one per test function, each directly after `monkeypatch.chdir(tmp_path)`.

- [ ] **Step 3: Run it**

```bash
pytest tests/test_update_causal_edge.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_update_causal_edge.py
git commit -m "Migrate test_update_causal_edge.py to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: migrate `tests/test_falsification_gate.py`

**Files:**
- Modify: `tests/test_falsification_gate.py`

- [ ] **Step 1: Replace the top-of-file block**

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py",
           "update_causal_edge.py", "record_falsification_check.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 2: Remove every `_copy_scripts(tmp_path)` call line** (two occurrences).

- [ ] **Step 3: Run it**

```bash
pytest tests/test_falsification_gate.py -v
```

Expected: both tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_falsification_gate.py
git commit -m "Migrate test_falsification_gate.py to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: migrate `tests/test_revise_fact_dispute_edge.py`

**Files:**
- Modify: `tests/test_revise_fact_dispute_edge.py`

- [ ] **Step 1: Replace the top-of-file block**

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "add_deduction.py",
           "propose_causal_edge.py", "revise_fact.py", "dispute_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 2: Remove every `_copy_scripts(tmp_path)` call line** (four occurrences).

- [ ] **Step 3: Run it**

```bash
pytest tests/test_revise_fact_dispute_edge.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_revise_fact_dispute_edge.py
git commit -m "Migrate test_revise_fact_dispute_edge.py to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: migrate `tests/test_review_queue_resolve_pending.py`

**Files:**
- Modify: `tests/test_review_queue_resolve_pending.py`

This file's `_run` is the same simple pattern as Tasks 6–8 (returns the raw
`CompletedProcess`; test bodies chain `.stdout.strip()` or read
`.returncode`/`.stderr` themselves) — it does **not** have
`test_golden_scenario.py`'s assert-and-return-string variant, confirmed by
inspection (`grep -n "^def _run" tests/test_review_queue_resolve_pending.py`
shows a bare `subprocess.run(...)` return, no internal assert). No
`_run_ok`-style wrapper is needed; every `.stdout.strip()` call site in the
file keeps working unchanged once `_run` is swapped for the shared helper.

- [ ] **Step 1: Replace the top-of-file block**

```python
old_string:
import json
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

ALL_SCRIPTS = (
    "add_evidence.py", "add_fact.py", "add_deduction.py", "propose_causal_edge.py",
    "update_causal_edge.py", "record_falsification_check.py",
    "revise_fact.py", "dispute_edge.py", "review_queue.py", "resolve_pending.py",
)


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ALL_SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
```

```python
new_string:
import json

from causal_graph import storage
from tests.cli_support import run_cli as _run
```

- [ ] **Step 2: Remove every `_copy_scripts(tmp_path)` call line** (ten occurrences, one per test function — everything else in each test body, including every `.stdout.strip()` chain, stays exactly as-is).

- [ ] **Step 3: Run it**

```bash
pytest tests/test_review_queue_resolve_pending.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_review_queue_resolve_pending.py
git commit -m "Migrate test_review_queue_resolve_pending.py to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: migrate `tests/test_golden_scenario.py`

**Files:**
- Modify: `tests/test_golden_scenario.py`

- [ ] **Step 1: Replace the top-of-file block**

```python
old_string:
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

ALL_SCRIPTS = (
    "add_evidence.py", "add_fact.py", "add_deduction.py", "propose_causal_edge.py",
    "update_causal_edge.py", "record_falsification_check.py",
    "revise_fact.py", "dispute_edge.py", "review_queue.py", "resolve_pending.py",
)


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ALL_SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    result = subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{script} {args} failed: {result.stderr}"
    return result.stdout.strip()
```

```python
new_string:
from causal_graph import storage
from tests.cli_support import run_cli as _run_raw


def _run(script, args, cwd):
    result = _run_raw(script, args, cwd)
    assert result.returncode == 0, f"{script} {args} failed: {result.stderr}"
    return result.stdout.strip()
```

(This file's `_run` already returns bare stdout everywhere it's called, so keep that exact signature/behavior — only its internals change to call the shared subprocess helper instead of `scripts/`.)

- [ ] **Step 2: Remove the single `_copy_scripts(tmp_path)` call line.**

- [ ] **Step 3: Run it**

```bash
pytest tests/test_golden_scenario.py -v
```

Expected: PASS, including the `len(audit) == 8` assertion (the audit log's `script` field now records subcommand names like `"add-fact"` instead of `"add_fact.py"` — the test doesn't assert on that field's value, only the count, so this is unaffected).

- [ ] **Step 4: Commit**

```bash
git add tests/test_golden_scenario.py
git commit -m "Migrate test_golden_scenario.py to the installed causal-graph command

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: delete `scripts/`, update AGENTS.md and README.md, full-suite verification

**Files:**
- Delete: `scripts/` (all 10 files)
- Modify: `AGENTS.md`
- Modify: `README.md`

**Interfaces:** none new — this is the cutover point where the old invocation surface is fully retired.

- [ ] **Step 1: Confirm nothing outside `scripts/` still references it**

```bash
grep -rn "scripts/" --include="*.py" . | grep -v .worktrees
```

Expected: no output (Tasks 5–10 already migrated every test file that had a match).

- [ ] **Step 2: Delete the directory**

```bash
git rm -r scripts/
```

- [ ] **Step 3: Update `AGENTS.md`** — replace every `python scripts/<name>.py ...` invocation example with the matching `causal-graph <subcommand> ...` form. Concretely, in the "Install" section replace:

```markdown
old_string:
There is no published package yet — install is always from a local
checkout via `pip install -e .`. After that, scripts are run from the repo
root as `python scripts/<name>.py ...` (not yet exposed as standalone
installed commands).
```

```markdown
new_string:
There is no published package yet — install is always from a local
checkout via `pip install -e .`. After that, the `causal-graph` command is
on `PATH` and runs from any working directory as
`causal-graph <subcommand> ...` (e.g. `causal-graph add-fact ...`).
```

In "The process" section, replace each fenced example, e.g.:

```markdown
old_string:
   python scripts/add_evidence.py --topic T --adapter <name> --content "..." --source-ref "..."
```

```markdown
new_string:
   causal-graph add-evidence --topic T --adapter <name> --content "..." --source-ref "..."
```

Apply the same `python scripts/<name>.py` → `causal-graph <subcommand-with-dashes>` substitution to every remaining fenced command in that section: `add_fact.py` → `add-fact`, `add_deduction.py` → `add-deduction`, `propose_causal_edge.py` → `propose-causal-edge`, `update_causal_edge.py` → `update-causal-edge`, `record_falsification_check.py` → `record-falsification-check`, `review_queue.py` → `review-queue`, `resolve_pending.py` → `resolve-pending`, and the "Corrections outside this flow" paragraph's `revise_fact.py`/`dispute_edge.py` → `revise-fact`/`dispute-edge`. Update the "Full CLI reference" table's left column from script filenames to subcommand names (same order, same descriptions).

- [ ] **Step 4: Update `README.md`'s quick-start snippet**

```markdown
old_string:
```bash
pip install -e .
python scripts/add_fact.py --topic my-topic --statement "..." \
  --evidence-id <id> --confidence verified
```
```

```markdown
new_string:
```bash
pip install -e .
causal-graph add-fact --topic my-topic --statement "..." \
  --evidence-id <id> --confidence verified
```
```

- [ ] **Step 5: Full verification**

```bash
pip install -e .
pytest -v
grep -rn "scripts/" AGENTS.md README.md .claude/skills/causal-graph-research/SKILL.md
```

Expected: full suite PASSes; the `grep` finds no remaining `scripts/` references in those three files.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Retire scripts/ in favor of the installed causal-graph CLI

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: canonical skill doc + Claude Code symlink

**Files:**
- Create: `skills/causal-graph-research/SKILL.md`
- Modify: `.claude/skills/causal-graph-research/SKILL.md` (replaced by a symlink)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Create the canonical skill doc**

```markdown
---
name: causal-graph-research
description: Use when investigating a research topic where an agent's tendency to form a verdict early and only seek confirming evidence would be costly — structures the investigation as an auditable fact/deduction graph plus a Bayesian-updated causal graph, mutated only through the deterministic `causal-graph` CLI.
---

# Causal Graph Research

The full process — install, storage model, step-by-step usage, the
falsification-gate retry pattern, the review queue, and the complete CLI
reference — lives in `AGENTS.md` at the repo root. It's written to be
agent-neutral (plain CLI, no SDK) so the same document works whether this
skill triggered you or a different agent opened the repo directly. Read
that file for the full picture; this SKILL.md exists so Claude Code,
Codex, and Cursor each auto-discover and surface it.

Keeping it simple: a simple question should be answerable with 1–2 calls
to `causal-graph add-fact` and nothing else — don't force adapters,
deductions, or causal edges onto a topic that doesn't need them.
```

- [ ] **Step 2: Replace the old file with a symlink to the new canonical one**

```bash
git rm .claude/skills/causal-graph-research/SKILL.md
ln -s ../../../skills/causal-graph-research/SKILL.md .claude/skills/causal-graph-research/SKILL.md
```

- [ ] **Step 3: Verify the symlink resolves correctly**

```bash
cat .claude/skills/causal-graph-research/SKILL.md
readlink .claude/skills/causal-graph-research/SKILL.md
```

Expected: `cat` prints the canonical file's content (proving the symlink target resolves); `readlink` prints `../../../skills/causal-graph-research/SKILL.md`.

- [ ] **Step 4: Commit**

```bash
git add skills/causal-graph-research/SKILL.md .claude/skills/causal-graph-research/SKILL.md
git commit -m "Consolidate causal-graph-research skill into one canonical doc

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 13: plugin manifests (Claude Code, Codex, Cursor) + validation test

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.codex-plugin/plugin.json`
- Create: `.cursor-plugin/plugin.json`
- Create: `tests/test_plugin_manifests.py`

**Interfaces:** none — static manifests + a test that reads them.

- [ ] **Step 1: Create `.claude-plugin/plugin.json`**

```json
{
  "name": "causal-graph-harness",
  "description": "Auditable fact/deduction graph plus a Bayesian-updated causal graph for structuring an agent's research investigation, so it doesn't lock onto an early verdict and only seek confirming evidence.",
  "version": "0.1.0",
  "author": {
    "name": "Zane"
  },
  "homepage": "https://github.com/hepzanechen/causal-graph-harness",
  "repository": "https://github.com/hepzanechen/causal-graph-harness",
  "license": "MIT",
  "keywords": [
    "research",
    "causal-graph",
    "bayesian",
    "falsification",
    "agent-harness"
  ]
}
```

- [ ] **Step 2: Create `.codex-plugin/plugin.json`**

```json
{
  "name": "causal-graph-harness",
  "version": "0.1.0",
  "description": "Auditable fact/deduction graph plus a Bayesian-updated causal graph for structuring an agent's research investigation, so it doesn't lock onto an early verdict and only seek confirming evidence.",
  "author": {
    "name": "Zane"
  },
  "homepage": "https://github.com/hepzanechen/causal-graph-harness",
  "repository": "https://github.com/hepzanechen/causal-graph-harness",
  "license": "MIT",
  "keywords": [
    "research",
    "causal-graph",
    "bayesian",
    "falsification",
    "agent-harness"
  ],
  "skills": "./skills/"
}
```

- [ ] **Step 3: Create `.cursor-plugin/plugin.json`**

```json
{
  "name": "causal-graph-harness",
  "displayName": "Causal Graph Harness",
  "description": "Auditable fact/deduction graph plus a Bayesian-updated causal graph for structuring an agent's research investigation, so it doesn't lock onto an early verdict and only seek confirming evidence.",
  "version": "0.1.0",
  "author": {
    "name": "Zane"
  },
  "homepage": "https://github.com/hepzanechen/causal-graph-harness",
  "repository": "https://github.com/hepzanechen/causal-graph-harness",
  "license": "MIT",
  "keywords": [
    "research",
    "causal-graph",
    "bayesian",
    "falsification",
    "agent-harness"
  ],
  "skills": "./skills/"
}
```

- [ ] **Step 4: Write `tests/test_plugin_manifests.py`**

```python
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

MANIFESTS = [
    REPO_ROOT / ".claude-plugin" / "plugin.json",
    REPO_ROOT / ".codex-plugin" / "plugin.json",
    REPO_ROOT / ".cursor-plugin" / "plugin.json",
]


def test_all_manifests_are_valid_json_with_required_fields():
    for path in MANIFESTS:
        data = json.loads(path.read_text())
        assert data["name"] == "causal-graph-harness"
        assert data["version"] == "0.1.0"


def test_codex_and_cursor_manifests_point_at_the_shared_skills_dir():
    # A manifest's "skills" path is relative to the plugin bundle root (the
    # repo root the manifest lives at the top of), not to the manifest
    # file's own directory — same convention obra/superpowers uses.
    for path in (REPO_ROOT / ".codex-plugin" / "plugin.json",
                 REPO_ROOT / ".cursor-plugin" / "plugin.json"):
        data = json.loads(path.read_text())
        skills_dir = (REPO_ROOT / data["skills"]).resolve()
        assert skills_dir == REPO_ROOT / "skills"
        assert (skills_dir / "causal-graph-research" / "SKILL.md").is_file()
```

- [ ] **Step 5: Run it**

```bash
pytest tests/test_plugin_manifests.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Run the full suite one last time**

```bash
pytest -v
```

Expected: every test in `tests/` PASSes.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/ .codex-plugin/ .cursor-plugin/ tests/test_plugin_manifests.py
git commit -m "Add Claude Code, Codex, and Cursor plugin manifests

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
