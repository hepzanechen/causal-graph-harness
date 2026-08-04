# AGENTS.md — Causal Graph Agent Harness

This file is the entrance point for **any** coding agent (not just Claude
Code) that finds itself in this repository. It is plain markdown and plain
CLI — no agent SDK, no vendor-specific framework required to use it.

**Status:** this is the only distribution mechanism right now (requires a
local git clone + `pip install -e .`). Per-agent plugin manifests and a
real package publish are scoped but intentionally deferred until the
skill/process itself is validated through real use — see "Future work:
cross-agent distribution" in the design spec.

## What this is

An auditable fact/deduction graph plus a Bayesian-updated causal graph for
structuring an investigation of a research question, so an agent doesn't
form a verdict early and only seek evidence that confirms it. All graph
mutation and Bayesian arithmetic is owned by deterministic Python scripts,
not by LLM output — the graph stays trustworthy regardless of which agent
or model drives the investigation.

Full design rationale:
`docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md`.

## When to use it

Use it when investigating a question where jumping to a single early
explanation would be costly, and you want to (a) keep facts, deductions,
and causal claims separately auditable, and (b) have confidence in a
causal claim earn its way up via evidence rather than assertion. For a
simple question, 1–2 calls to `add_fact.py` and nothing else is a
legitimate, complete use — don't force the rest of the pipeline.

## Install

```bash
git clone <this repo>   # or: cd into an existing checkout
pip install -e .
```

Requires Python >= 3.10. No third-party runtime dependencies (`pytest` is
dev-only, for running the test suite).

There is no published package yet — install is always from a local
checkout via `pip install -e .`. After that, the `causal-graph` command is
on `PATH` and runs from any working directory as
`causal-graph <subcommand> ...` (e.g. `causal-graph add-fact ...`).

**Sandbox quirk:** if `pytest` isn't resolvable after install, run it as a
module with user site-packages re-enabled:
`PYTHONNOUSERSITE= python3 -m pytest -v`.

## How storage works

Everything lives under `research/<topic>/graph/` relative to the current
working directory when you invoke a script — pick a short topic slug
(e.g. `etl-oom-failure`) and pass it as `--topic <slug>` to every call.
This directory is created on first use; no separate server or daemon.

## The process

Steps 2 and 5–7 are conditional — skip what a simple question doesn't
need.

1. **Define the research question.** Pick the topic slug.
2. **Elicit human input (optional, skippable).** If a human gives you
   known facts/evidence, register them via `add_evidence.py`/`add_fact.py`
   like any other source. If they give you a hunch/suspected cause,
   register it as a deduction or causal-edge proposal with an explicit
   neutral/low prior (e.g. 0.3, not 0.8) — a hypothesis to test, not a
   starting verdict. Skip this step entirely for autonomous investigation.
3. **Gather evidence**, then register each item:
   ```
   causal-graph add-evidence --topic T --adapter <name> --content "..." --source-ref "..."
   ```
   - Local repo: use your own grep/read tools (or
     `adapters.codebase_adapter.CodebaseAdapter`), register with
     `--adapter codebase`.
   - Web: use your own web-search tool, register with `--adapter
     external_web --source-ref <url>`.
   - Human-asserted: `--adapter human --source-ref "conversation:<date>"`.
   - `InternalDBAdapter` / `ManualDocAdapter` / `ExperimentResultsAdapter`
     in `adapters/` are stubs (raise `NotImplementedError`) until wired to
     a real backend — register that evidence manually via `add_evidence.py`
     in the meantime.
4. **Extract facts:**
   ```
   causal-graph add-fact --topic T --statement "..." --evidence-id <id> --confidence {verified|reported|inferred}
   ```
   If a new fact structurally contradicts an existing one, add
   `--contradicts <fact_id>` — this queues it for review instead of
   letting both facts stand as active simultaneously.
5. **Propose deductions** (skip if there's no multi-fact claim to make):
   ```
   causal-graph add-deduction --topic T --claim "..." --supports "fact:ID,fact:ID2"
   ```
6. **Propose causal edges** (skip if there's no causal claim to make):
   ```
   causal-graph propose-causal-edge --topic T --from fact:ID|deduction:ID --to fact:ID|deduction:ID --relation-type "contributes-to" --prior 0.3
   ```
   Priors start neutral-to-low; they earn confidence through evidence, not
   assertion.
7. **Update edges as evidence arrives:**
   ```
   causal-graph update-causal-edge --topic T --edge-id ID --evidence-id ID --likelihood-ratio N [--correlated-with "id1,id2"]
   ```
   - Use `--correlated-with` when new evidence isn't independent of prior
     evidence already applied to this edge (e.g. two reports from the same
     underlying source) — prevents double-counting.
   - If the command prints `queued for review: ...`, the update was **not**
     applied. Common reasons: it would cross the high-confidence threshold
     without a recorded falsification check, or it reverses the edge's
     trend sharply. For the falsification case, run
     `causal-graph record-falsification-check --topic T --edge-id ID --alternative-hypothesis "..." --counterevidence-search "..." --result "..."`
     (a genuine null result is a valid answer) and retry the same update
     call.
8. **Check and act on the review queue periodically:**
   ```
   causal-graph review-queue --topic T
   ```
   lists pending items with a computed `tier`.
   - `urgent` items (high graph impact): surface to the human immediately,
     don't wait for a periodic summary.
   - `normal` items: mention the count in your next summary; resolve with
     `causal-graph resolve-pending --topic T --id ID --action {approve|reject|amend} [--amended-likelihood-ratio N]`.

Corrections outside this flow: `causal-graph revise-fact` (retract/contest/
supersede a fact) and `causal-graph dispute-edge` (retract/contest/
supersede a causal edge) — both cascade a `stale` status to everything
downstream in the same call.

## Full CLI reference

Ten subcommands of the installed `causal-graph` command, all following the
same pattern: read current state, validate, write via one atomic
operation, print the new record's ID (or `queued for review: <id>` if
diverted) on stdout, a clear `error: ...` on stderr and non-zero exit on
failure.

| Subcommand | Purpose |
|---|---|
| `add-evidence` | Register a raw evidence item from any source |
| `add-fact` | Extract a grounded fact from evidence (or flag a contradiction) |
| `add-deduction` | Propose a multi-fact inference |
| `propose-causal-edge` | Propose a causal claim between two nodes with a prior |
| `update-causal-edge` | Apply a Bayesian update to an edge's posterior |
| `record-falsification-check` | Record a counter-evidence search (required before an edge can autonomously cross the high-confidence threshold) |
| `revise-fact` | Retract/contest/supersede a fact |
| `dispute-edge` | Retract/contest/supersede a causal edge |
| `review-queue` | List items diverted for human review, with urgency tier |
| `resolve-pending` | Approve/reject/amend a queued item |

See `README.md` for a worked end-to-end walkthrough of the first six.

## Claude Code specifically

If you're running as Claude Code in this repo, `.claude/skills/causal-graph-research/SKILL.md`
is auto-discovered and points back at this file — you don't need to do
anything differently, the content is the same either way.
