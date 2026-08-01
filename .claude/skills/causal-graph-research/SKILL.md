---
name: causal-graph-research
description: Use when investigating a research topic where an agent's tendency to form a verdict early and only seek confirming evidence would be costly — structures the investigation as an auditable fact/deduction graph plus a Bayesian-updated causal graph, mutated only through deterministic scripts in scripts/.
---

# Causal Graph Research

The full process — install, storage model, step-by-step usage, the
falsification-gate retry pattern, the review queue, and the complete CLI
reference — lives in `AGENTS.md` at the repo root. It's written to be
agent-neutral (plain CLI, no SDK) so the same document works whether this
skill triggered you or a different agent opened the repo directly. Read
that file for the full picture; this SKILL.md exists only so Claude Code
auto-discovers and surfaces it.

Keeping it simple: a simple question should be answerable with 1–2 calls
to `add_fact.py` and nothing else — don't force adapters, deductions, or
causal edges onto a topic that doesn't need them.
