# Causal Graph Agent Harness — Design

Date: 2026-08-01
Status: Approved (pending user spec review)
Related: `research/agent-reasoning-bias/graph-based-root-cause-analysis.md`

## Problem

LLM agents investigating a research topic tend to explore context, form a
verdict early, then search for evidence that supports that verdict — rather
than considering deeper root causes or multiple contributing factors. Prior
research (see related doc above) shows this bias lives in **evidence
selection**, not evidence weighing, and that graph-structured reasoning plus
an explicit falsification step is the field's converged-on countermeasure.

This design specifies a harness that structures agent investigation as an
explicit fact/deduction graph plus a probabilistic causal graph, with
deterministic (non-LLM) code owning the graph mutations and math, so the
result is auditable and its arithmetic trustworthy regardless of which
agent/model drove the investigation.

## Goals

- Support arbitrary research topics with **pluggable evidence sources**
  (internal DB, local codebase, manuals/docs, experiment results, external
  web/domain knowledge) — not hardcoded to one domain.
- Be **portable across different driving agents/models** — the state and
  mutation logic must not be tied to one agent SDK.
- Keep the **arithmetic and structural integrity deterministic** (code, not
  LLM output) for anything that affects trust: Bayesian updates, referential
  integrity, schema validation.
- Let **humans participate on equal footing** with agents as evidence
  sources, and give humans explicit review/correction/override points.
- Stay usable for **small, simple problems** without forcing the full
  pipeline — every layer beyond basic fact-recording is optional per use.

## Non-goals (out of scope for this design)

- Automated contrarian/debate agent role (deferred — see "Future: gate"
  below; only the *hook* for it is built now).
- Any UI or visualization of the graph.
- Distributed/concurrent multi-writer support beyond a simple per-topic file
  lock.
- Real implementations of `InternalDBAdapter`, `ManualDocAdapter`,
  `ExperimentResultsAdapter` — interface + stub only, wired to real systems
  later.

## Architecture

Four layers:

1. **Evidence adapters** — pluggable modules, each implementing
   `fetch(query) -> list[EvidenceRecord]`. Auto-discovered from an
   `adapters/` directory (or a manifest) rather than hardcoded/enumerated in
   core code, so adding a new source means dropping in a file, not editing a
   switch statement.
2. **State layer** — the graphs live as plain JSON/JSONL files per research
   topic, not a database. Inspectable, diffable, git-friendly.
3. **Deterministic mutation layer** — Python CLI scripts are the *only* way
   to write to state. They own schema validation, referential integrity, and
   exact Bayes-rule arithmetic. Any agent (or human) invokes them via Bash.
4. **Process layer** — a skill (markdown instructions) telling whichever
   agent is driving *when* to call adapters and scripts. This is the
   portable part: swap the driving agent/model, the skill and scripts don't
   change.

## Data model

Two graphs, not three — despite "fact graph / deduction graph / causal
graph" framing in earlier research, deductions are structurally just nodes
downstream of facts, so they form one connected grounding graph:

1. **Grounding graph** (deterministic, no probabilities) — facts +
   deductions, connected by "derived-from" edges (a deduction's
   `supporting_fact_ids[]` / `supporting_deduction_ids[]`). Pure
   traceability: "this claim rests on these facts."
2. **Causal graph** (probabilistic) — a separate edge type
   (`causal_edges.json`) over nodes drawn from the grounding graph, each
   edge carrying a `prior`/`posterior` that gets Bayesian-updated as
   evidence arrives.

**Only facts and deductions are nodes.** Evidence is never a node in either
graph — it's a flat, cited leaf store that facts point into
(`evidence_ids[]`). A causal edge can connect any combination of fact/
deduction nodes (fact→fact, deduction→fact, deduction→deduction, etc.), so
node identity carries its own type instead of a separate type field: IDs
are prefixed, e.g. `"fact:f1"`, `"deduction:d1"`.

Per-topic storage: `research/<topic>/graph/`
- `facts.json` — `{id, statement, evidence_ids[], confidence: verified|reported|inferred, created_at, created_by}`
- `evidence.json` — `{id, content, source_adapter, source_ref, retrieved_at}`
- `deductions.json` — `{id, claim, supporting_fact_ids[], supporting_deduction_ids[], logic_note, created_at, created_by}`
- `causal_edges.json` — `{id, from_node, to_node, prior, posterior, updates: [{evidence_id, likelihood_ratio, agent, timestamp}], last_updated}` — `from_node`/`to_node` are type-prefixed IDs (`"fact:f1"`, `"deduction:d1"`)
- `audit_log.jsonl` — append-only, one line per mutation call:
  `{timestamp, agent_id, script, args, result}`
- `pending_review.jsonl` — queued items requiring human review (see below)

`source_adapter` (on `evidence.json` only — see below) is a free-text name,
not a closed enum, so adapters are not hardcoded into the schema or scripts.
`facts.json` deliberately has no `source_adapter` field: it's derivable via
`evidence_ids` → `evidence.json`, and a fact can cite evidence from more
than one adapter, so a single value on the fact itself would be either
redundant or wrong.

The causal edge's `posterior` is always computed by the script from
`prior × likelihood_ratio` (normalized). Agents/humans supply a
likelihood-ratio *estimate* for a piece of evidence, never the posterior
directly — this is what keeps the arithmetic honest regardless of which
model is driving.

## Deterministic scripts (Python CLI)

- `add_evidence.py --adapter <name> --content ... --source-ref ...`
- `add_fact.py --statement ... --evidence-id ... --confidence ...`
- `add_deduction.py --claim ... --supports fact:ID,deduction:ID2`
- `propose_causal_edge.py --from fact:ID|deduction:ID --to fact:ID|deduction:ID --prior ...`
- `update_causal_edge.py --edge-id ... --evidence-id ... --likelihood-ratio ...`
  (computes exact Bayes posterior; may divert to `pending_review.jsonl`
  instead of applying — see Review & urgency below)
- `revise_fact.py` / `dispute_edge.py` — mark an existing entry
  superseded/contested with a reason; never silently overwrite, preserving
  audit history
- `review_queue.py` — list pending items
- `resolve_pending.py --id X --approve|--reject|--amend`

Each script: validates schema + referential integrity + probability bounds
`[0,1]`, writes atomically (temp file + rename), appends to
`audit_log.jsonl`, and exits non-zero with a clear message on invalid input
(no partial writes).

## Evidence adapters

Interface: `fetch(query) -> list[EvidenceRecord]`. Built now:
- `ExternalWebAdapter` — wraps WebSearch/WebFetch.
- `CodebaseAdapter` — greps/reads the local repo; `source_ref` is a file
  path + line range.

Stubbed (interface only, wired to real systems later):
- `InternalDBAdapter`, `ManualDocAdapter`, `ExperimentResultsAdapter`.

**Humans are not a "fetch" adapter.** Human-provided evidence is asserted
directly in conversation, not queried, so it flows through the same
`add_evidence.py` / `add_fact.py` scripts as any adapter output, with
`source_adapter="human"` and `source_ref` pointing at the
conversation/session. Same schema, same confidence tiers, same audit trail
— humans and agents are on equal footing as evidence sources; only the
source tag differs.

## Process skill

A skill (`causal-graph-research`) that any driving agent follows:

1. Define the research question; create/open the topic folder.
2. **Elicit human input (optional, skippable).** Ask the human for (a) any
   known facts/evidence they already have, and (b) any suspected
   cause/hypothesis. (a) registers via `add_evidence.py`/`add_fact.py` on
   equal footing with anything an adapter would return. (b) registers as a
   deduction or causal-edge proposal with an explicit neutral/low prior — a
   hypothesis to test, not a starting verdict, so a human's hunch gets a
   head start on being *considered*, not on being *believed*. This step is
   valuable when the human is a domain expert with material the agent would
   otherwise have to rediscover, and is fully skippable for simple problems
   or when the human wants the agent to discover and decide everything
   autonomously — the agent then proceeds straight to step 3 unprompted.
3. Run relevant adapters (or accept human-asserted evidence); register via
   `add_evidence.py`.
4. Extract candidate facts from evidence → `add_fact.py`.
5. Propose deductions from facts → `add_deduction.py`.
6. Propose causal edges between grounded nodes → `propose_causal_edge.py`.
7. For each new piece of evidence bearing on an edge, estimate a likelihood
   ratio and call `update_causal_edge.py` (script does the Bayes math; may
   queue for review instead of applying).
8. Periodically summarize graph state for human review, including any
   pending-review queue count.

Steps are **conditional, not mandatory** — see Scope & simplicity below.

## Human review & urgency tiering

All state mutation goes through the same CLI scripts whether called by an
agent or a human, so humans have full access to review, correct
(`revise_fact.py` / `dispute_edge.py`), and resolve queued items
(`resolve_pending.py`) without any separate UI.

**Review triggers** — a script diverts a change to `pending_review.jsonl`
instead of applying it when:
- A causal edge's posterior is about to cross a high-confidence threshold
  (the gate).
- New evidence would reverse an edge's trend by more than a configured
  margin (default: posterior odds shift by more than 2x in the opposite
  direction from the prior's trend).
- An agent attempts to modify/retract a fact previously marked `verified`
  by a human.
- Two facts or deductions are structurally contradictory.

**Urgency tiering** — each queued item is also tagged by an **impact
score**: the count of downstream deductions + causal edges that transitively
depend on the node (reachability in the grounding + causal graph combined).
Tier is **relative to current graph size** (percentile rank, e.g. default
top 10% of nodes by dependents = `urgent`), with a floor: **below a minimum
graph size (default 8 nodes), urgency tiering does not trigger** — in a
small graph the human sees everything in one summary anyway, so computing
centrality adds process without adding signal.

- `urgent` items: the process skill has the driving agent surface it in the
  current session immediately, not wait for the periodic summary; if the
  agent is running unattended, it uses a push notification.
- `normal` items: stay batched in `pending_review.jsonl`, surfaced at the
  next periodic summary.

**Future: automated gate.** Not built now. The hook is the same
`pending_review.jsonl` mechanism — a later automated contrarian/falsification
pass can resolve `normal`-tier items the same way a human does via
`resolve_pending.py`, without changing the schema or the scripts that
produce the queue.

## Scope & simplicity (standing design rule)

Every layer beyond basic fact-recording is **optional per use**, not a
mandatory pipeline:
- The smallest legitimate use is calling `add_fact.py` a few times and
  stopping — no adapters, deductions, or causal edges required.
- The process skill's steps are conditional: skip steps that don't apply
  (e.g. no causal claim to make → skip steps 5/6 entirely) rather than
  forcing every topic through all seven steps.
- Pending-review and urgency tiering only activate once a causal graph with
  real structure exists; a pure fact-gathering session never touches that
  machinery.
- The initial human-elicitation step (process skill step 2) is opt-in: a
  user can tell the agent to skip straight to autonomous, adapter-driven
  discovery, letting the agent find and decide everything itself.

**Rule for implementation:** the full pipeline is for topics complex enough
to need it; a simple question must be answerable with 1-2 script calls and
nothing else, and no part of the design may force heavier layers to be
present or configured before the simple path works.

## Error handling

- Schema validation, referential integrity, and probability-bounds checks
  before any write.
- Atomic writes (temp file + rename) — no partial/corrupt state on crash.
- Invalid input → non-zero exit, clear stderr message, nothing written.
- Concurrency: a simple per-topic file lock (flock); documented as
  "single active writer per topic," not distributed locking. Revisit only if
  this proves insufficient in practice.

## Testing

- `pytest` unit tests per script: valid input; rejected invalid references;
  rejected out-of-bounds probabilities; Bayes-update arithmetic checked
  against hand-computed examples.
- One golden-scenario test: a small scripted pipeline (2 facts → 1 deduction
  → 1 causal edge updated by 2 pieces of evidence) asserting final JSON
  matches an expected snapshot.
- Adapter contract tests for `ExternalWebAdapter` and `CodebaseAdapter`
  (mocked underlying calls; just checking well-formed `EvidenceRecord`
  output).
