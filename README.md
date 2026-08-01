# Causal Graph Agent Harness

An auditable fact/deduction graph plus a Bayesian-updated causal graph for
structuring an agent's (or human's) investigation of a research question.
It exists to counter a specific failure mode: an agent forms a verdict early
and then only seeks evidence that confirms it. All graph mutations and the
Bayesian math are owned by deterministic Python code, not LLM output, so the
resulting graph is auditable and its arithmetic trustworthy regardless of
which agent or model drove the investigation. See
`docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md` for
the full design rationale.

## Setup

```bash
pip install -e .
pip install pytest   # only needed to run the test suite
```

Requires Python >= 3.10.

**Environment quirk:** in some sandboxes `pytest` isn't on `PATH` correctly
after install. If plain `pytest` doesn't work, run it as a module with user
site-packages disabled instead:

```bash
PYTHONNOUSERSITE= python3 -m pytest -v
```

## Golden path walkthrough

Everything is driven through the CLI scripts under `scripts/`; there is no
separate server or daemon. Each script prints the new record's ID on success
— capture it in a shell variable to reference in later commands. This
sequence (2 evidence -> 2 facts -> 1 deduction -> 1 causal edge -> 2
Bayesian updates) mirrors `tests/test_golden_scenario.py`, the one
end-to-end scenario proven by the test suite:

```bash
# 1. Register evidence
ev1=$(python scripts/add_evidence.py --topic etl --adapter internal_db \
  --content "ETL pod OOM-killed at 02:14 UTC" --source-ref "k8s-events/etl-worker-7")

ev2=$(python scripts/add_evidence.py --topic etl --adapter codebase \
  --content "memory limit cut 4Gi to 2Gi in PR #482" --source-ref "deployment.yaml:12")

# 2. Extract grounded facts from that evidence
f1=$(python scripts/add_fact.py --topic etl --statement "ETL job OOM-killed at 02:14 UTC" \
  --evidence-id "$ev1" --confidence verified)

f2=$(python scripts/add_fact.py --topic etl --statement "Memory limit reduced 4Gi to 2Gi" \
  --evidence-id "$ev2" --confidence verified)

# 3. Propose a deduction supported by a fact
d1=$(python scripts/add_deduction.py --topic etl --claim "Memory headroom shrank" \
  --supports "fact:$f2" --logic-note "limit halved")

# 4. Propose a causal edge with a neutral prior
e1=$(python scripts/propose_causal_edge.py --topic etl --from "deduction:$d1" --to "fact:$f1" \
  --relation-type "contributes-to" --prior 0.3)

# 5. Update the edge's posterior as each piece of evidence bears on it
python scripts/update_causal_edge.py --topic etl --edge-id "$e1" \
  --evidence-id "$ev1" --likelihood-ratio 3.0
python scripts/update_causal_edge.py --topic etl --edge-id "$e1" \
  --evidence-id "$ev2" --likelihood-ratio 2.0
```

After this, `research/etl/graph/causal_edges.json` holds the edge with both
updates applied and its posterior moved above the 0.3 prior.

There are ten CLI scripts total under `scripts/`: the six used above, plus
`revise_fact.py` and `dispute_edge.py` (corrections), and
`review_queue.py` / `resolve_pending.py` (for items a script diverts to
human review instead of applying automatically — e.g. an update that would
cross a high-confidence threshold without a recorded falsification check).

## Full workflow for driving agents

`AGENTS.md` at the repo root is the agent-neutral entrance point: it
documents install, the storage model, the complete step-by-step process
(eliciting human input, gathering evidence per source, the
falsification-gate retry pattern for high-confidence updates, working the
review queue), and the full CLI reference. Read that for the full picture
rather than this README — it works the same whether you're Claude Code
(which also auto-discovers `.claude/skills/causal-graph-research/SKILL.md`,
a thin pointer at the same content) or any other agent that can read a repo
and run shell commands.

## Adapters

`adapters/` provides `CodebaseAdapter` (a real, working local-repo grep
adapter) plus stub interfaces — `InternalDBAdapter`, `ManualDocAdapter`,
`ExperimentResultsAdapter` — that raise until wired to a real backend.
`external_web` and `human` are not code; they're adapter tags used when an
agent registers evidence it gathered itself (via its own web-search tool, or
from a human) with `add_evidence.py --adapter external_web|human`.

## Where state lives

Each topic's live investigation state is written to
`research/<topic>/graph/` (`facts.json`, `evidence.json`, `deductions.json`,
`causal_edges.json`, `audit_log.jsonl`, `pending_review.jsonl`, `_meta.json`,
`.lock`). This is runtime output, not source — `research/*/graph/` is
gitignored so it won't collide with committed docs that live directly under
`research/<topic>/` (outside a `graph/` subdirectory).
