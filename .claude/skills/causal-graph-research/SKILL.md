---
name: causal-graph-research
description: Use when investigating a research topic where an agent's tendency to form a verdict early and only seek confirming evidence would be costly — structures the investigation as an auditable fact/deduction graph plus a Bayesian-updated causal graph, mutated only through deterministic scripts in scripts/.
---

# Causal Graph Research

Follow these steps. Steps 2 and 5–7 are conditional — skip what a simple
question doesn't need; see "Keeping it simple" below.

1. **Define the research question.** Pick a short topic slug (e.g.
   `etl-oom-failure`); every script call below takes `--topic <slug>`.

2. **Elicit human input (optional, skippable).** Ask the user for (a) any
   known facts/evidence they already have, and (b) any suspected
   cause/hypothesis.
   - (a) Register directly via `add_evidence.py` / `add_fact.py`, same as
     any other source.
   - (b) Register as a deduction or causal-edge proposal with an explicit
     neutral/low prior (e.g. 0.3, not 0.8) — a hypothesis to test, not a
     starting verdict.
   - Skip this step entirely if the user wants you to discover and decide
     everything autonomously.

3. **Gather evidence.** For each source:
   - Local repo: use your own grep/read tools (or `adapters.codebase_adapter.CodebaseAdapter`),
     then register each finding with `python scripts/add_evidence.py --topic T --adapter codebase --content "..." --source-ref "path:line"`.
   - Web: use your own web-search tool, then register with `--adapter external_web --source-ref <url>`.
   - Human-asserted: `--adapter human --source-ref "conversation:<date>"`.
   - `InternalDBAdapter` / `ManualDocAdapter` / `ExperimentResultsAdapter` are stubs — only use them once wired to a real backend; otherwise register that evidence manually too.

4. **Extract facts.** For each evidence item, if it supports a grounded
   claim: `python scripts/add_fact.py --topic T --statement "..." --evidence-id <id> --confidence {verified|reported|inferred}`.
   If a new fact structurally contradicts an existing one, add
   `--contradicts <fact_id>` — this queues it for review rather than
   silently coexisting.

5. **Propose deductions** (skip if there's no multi-fact claim to make):
   `python scripts/add_deduction.py --topic T --claim "..." --supports "fact:ID,fact:ID2"`.

6. **Propose causal edges** (skip if there's no causal claim to make):
   `python scripts/propose_causal_edge.py --topic T --from fact:ID|deduction:ID --to fact:ID|deduction:ID --relation-type "contributes-to" --prior 0.3`.
   Priors start neutral-to-low; they earn confidence through evidence, not assertion.

7. **Update edges as evidence arrives:**
   `python scripts/update_causal_edge.py --topic T --edge-id ID --evidence-id ID --likelihood-ratio N [--correlated-with "id1,id2"]`.
   - Use `--correlated-with` when new evidence isn't independent of prior
     evidence already applied to this edge (e.g. two reports from the same
     underlying source) — this prevents double-counting.
   - If the command prints `queued for review: ...`, the update was **not**
     applied. Common reasons: it would cross the high-confidence threshold
     without a recorded falsification check, or it reverses the edge's
     trend sharply. For the falsification case, run
     `python scripts/record_falsification_check.py --topic T --edge-id ID --alternative-hypothesis "..." --counterevidence-search "..." --result "..."`
     (a genuine null result is a valid answer) and retry the update.

8. **Check and act on the review queue periodically:**
   `python scripts/review_queue.py --topic T` lists pending items with a
   computed `tier`.
   - `urgent` items (high graph impact): surface to the human immediately
     in this session — don't wait for a periodic summary.
   - `normal` items: mention the count in your next summary; resolve with
     `python scripts/resolve_pending.py --topic T --id ID --action {approve|reject|amend} [--amended-likelihood-ratio N]`.

## Keeping it simple

The full pipeline is for topics complex enough to need it. A simple
question should be answerable with 1–2 calls to `add_fact.py` and nothing
else — don't force evidence adapters, deductions, or causal edges onto a
topic that doesn't need them.
