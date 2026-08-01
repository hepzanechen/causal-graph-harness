# Causal Graph Agent Harness — Implementation Review

Date: 2026-08-01  
Reference specification: `docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md`

## Scope and method

This was a static read-through of the local package, CLI scripts, adapters,
process skill, documentation, and existing tests. No tests were added or run,
and no implementation files were changed. The older untracked design review in
`docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design-review.md`
was treated as historical context and was not modified.

## Executive verdict

The implementation has a sound portable core: plain files, stdlib-only Python,
shell-facing CLIs, free-text source names, and no dependency on an agent SDK.
The append-first audit design and the optional fact-only path also follow the
specification's main architectural direction.

It is **not yet fully compliant or safely pluggable as specified**. The most
important gaps are in lifecycle correctness, contradiction/review handling,
Bayesian input validation, and adapter/process discovery. Several performance
paths also become quadratic as a topic or its audit history grows.

## Highest-priority correctness and specification gaps

### 1. [P1] Contradictory facts are applied before review and cannot be resolved

- `scripts/add_fact.py:37-51` writes the new fact as `active` and merely adds a
  queue item. The spec requires the conflicting change to be diverted instead
  of applied (`design.md:216-225`).
- `scripts/resolve_pending.py:28-46` has no `contradiction` branch. Approve,
  reject, and amend all delete the queue item without changing either fact.
- Contradictory deductions are not representable at all, although the trigger
  explicitly covers facts **or deductions**.

Impact: the current graph can simultaneously present contradictory facts as
active, and the advertised human correction point cannot settle the conflict.

### 2. [P1] Inactive nodes are still accepted as current dependencies

`add_deduction.py`, `propose_causal_edge.py`, and `update_causal_edge.py` check
only that IDs exist; none require referenced nodes or the updated edge to be
`active`. After a retraction, an agent can therefore create a new active
deduction from a retracted fact, create an active edge over stale nodes, or
continue updating a stale/retracted edge. Updating a stale edge also leaves its
status stale, so the specified explicit reaffirmation path is absent.

This conflicts with `design.md:300-310`, which says stale entries are excluded
from the current view until recomputed or explicitly reaffirmed.

### 3. [P1] Retraction propagation misses an edge whose target is invalidated

`causal_graph/graph.py:32-39` marks an edge dependent only when its
`from_node` is reachable. A causal edge structurally depends on both endpoints:
if the retracted fact/deduction is the edge's `to_node`, the edge remains
`active` even though one of its referenced nodes is no longer current. Existing
tests cover only the `from_node` direction.

### 4. [P1] Pending amendments bypass likelihood-ratio validation

`scripts/resolve_pending.py:33-39` writes
`--amended-likelihood-ratio` directly into an update without calling
`validate_likelihood_ratio`. Zero, negative, `nan`, or `inf` values can produce
an invalid posterior and commit it, violating the pre-write probability and
schema guarantees at `design.md:336-340`. The normal update path validates only
positivity and should also reject non-finite values.

### 5. [P2] Correlated counterevidence selects the weaker ratio

`causal_graph/bayes.py:41-43` uses numeric `max()` as the strongest likelihood
ratio. For two correlated pieces of counterevidence with ratios `0.5` and
`0.01`, the stronger evidence is `0.01` (farther from neutral on the log-odds
scale), but the code chooses `0.5`. This understates correlated negative
evidence and makes the posterior directionally inconsistent with the spec's
“strongest single likelihood ratio” rule.

### 6. [P2] Correlation claims have no referential-integrity check

`scripts/update_causal_edge.py:28-49` accepts any `--correlated-with` IDs.
Unknown IDs and evidence not previously applied to that edge are silently
ignored by `group_correlated`, so the stored declaration can say “correlated”
while the arithmetic treats the update as independent. Duplicate reuse of the
same evidence ID is also not rejected. This breaks the explicit independence
contract in `design.md:282-290`.

### 7. [P2] The documented falsification retry leaves a live duplicate queue item

The skill tells an agent to record a falsification check and retry a diverted
update (`.claude/skills/causal-graph-research/SKILL.md:50-55`). The retry can
apply, but `update_causal_edge.py:51-75` never removes or supersedes the original
pending item. The queue therefore continues to report work that has already
been applied, and later approval can append the same evidence again.

### 8. [P2] High-confidence crossing is not always sent to human review

`update_causal_edge.py:11-16` queues a threshold crossing only when the edge has
no falsification check. The specification lists threshold crossing as a review
trigger in its own right and missing falsification as an additional trigger
(`design.md:216-225,258-267`). With a check present, the current code applies the
crossing automatically instead of diverting it for review.

### 9. [P2] Queued verified-fact revisions lose data and misidentify provenance

- `scripts/revise_fact.py:28-42` classifies every `verified` fact as
  human-verified, even though any agent can create one; it does not inspect
  `created_by` or another human-verification marker.
- If `--replacement-statement` is supplied, that value is not stored in the
  pending item. Approval in `resolve_pending.py` changes only the old status,
  so the proposed replacement disappears.

### 10. [P2] Topic names can escape the specified storage root

`causal_graph/topic.py:14-20` joins an unvalidated topic directly into a path.
Absolute topics or `..` segments can place graph state outside
`research/<topic>/graph/`. This is especially risky when an agent generates the
topic slug. Enforce a slug/path-containment invariant before taking the lock or
writing files.

## Agent and adapter pluggability assessment

### What is already portable

- State is agent-neutral JSON/JSONL and mutation is exposed through Bash CLIs.
- `CAUSAL_GRAPH_AGENT_ID` is generic and there are no Claude/OpenAI SDK imports.
- `source_adapter` is free text, so evidence records do not require schema
  changes for every source.
- `EvidenceRecord` plus `fetch(query)` is a small adapter contract.

### What prevents drop-in pluggability

1. **No adapter discovery or manifest exists.** The spec requires modules to be
   auto-discovered so a source can be added by dropping in a file
   (`design.md:54-58`). The repository provides classes, but no loader,
   registry, manifest, adapter runner, or contract validation. Agents must know
   and import each module manually.
2. **The process skill is installed only under `.claude/skills/`.** The content
   is mostly agent-neutral, but its location is provider-specific and it is not
   packaged by `pyproject.toml`. A different agent will not discover it without
   bespoke setup or a direct path supplied by a human.
3. **The CLIs are not package entry points.** `pip install` installs
   `causal_graph` and `adapters`, while the documented interface remains
   `python scripts/...` from a repository checkout. This is usable locally but
   not a self-contained harness install for another agent environment.
4. **CLI output has no stable machine-readable envelope.** Success may print an
   ID or prose such as `queued for review`, while queued work still exits zero.
   Agents can follow the current skill, but generic orchestrators must rely on
   text matching rather than a status/ID schema.

Overall: **agent-neutral internally, but not yet plug-and-play across agent
runtimes or evidence plugins**.

## Performance headroom

### A. Audit repair is linear in all history on every command

`storage.prepare()` calls `repair()`, and `repair()` parses the complete audit
log before slicing at `applied_through` (`causal_graph/storage.py:100-115`). The
spec calls this a cheap consistency check, but command latency grows with every
mutation. Track a durable byte offset/event sequence and read only the tail.

### B. Snapshot mutation and lifecycle invalidation can become quadratic

Each `upsert()` loads and rewrites an entire JSON array. A lifecycle operation
producing many writes invokes this once per dependent, often repeatedly for the
same file. Group writes by snapshot key, apply them in memory, and atomically
rewrite each affected file once per committed event.

### C. Audit entries duplicate complete aggregate records

Every edge update logs the full edge, including all previous `updates[]` and
falsification checks. Repeated updates therefore produce roughly quadratic
audit-log growth before the full-log read cost is considered. Store a compact
mutation delta/event in the authoritative log and derive the aggregate edge in
the snapshot replay.

### D. Urgency scoring repeatedly reloads and rescans the graph

`urgency_tier()` calls `downstream_dependents()` for every node, and every call
reloads all snapshot files and repeatedly scans all deductions and edges.
`review_queue.py` repeats that process for every queued item. Build adjacency
maps once per queue listing and compute all reachability counts from that
in-memory graph. Also handle percentile ties explicitly: the current `<=`
ranking can mark every node urgent when all impact counts are equal.

### E. CodebaseAdapter performs an unbounded full-tree Python scan

`CodebaseAdapter.fetch()` opens every file under the root, ignores only four
directory names, and returns every match. Large repos, build outputs, vendored
trees, and binary files will dominate runtime and memory. Within the stdlib-only
constraint, add configurable ignore patterns, file-size/type limits, and a
result cap; where allowed, an optional ripgrep-backed implementation would be a
substantial speedup.

## Additional compliance notes

- `pending_review.jsonl` is implemented as one JSON array rewritten in place,
  not JSON Lines. That contradicts the filename/data-model contract and can
  break external tooling that reads one object per line.
- Queue records are initially hardcoded to `tier: normal` and contain no
  `impact_score`; urgency is computed only for display. The spec says each
  queued item is tagged with both impact and relative urgency.
- `add_deduction.py` accepts an empty `--supports` value, allowing an ungrounded
  deduction despite the grounding-graph model.
- A replacement fact can point through `supersedes_id` while the old fact is
  left `contested` or `retracted`; the spec says the replaced entry is
  superseded, so the lifecycle invariant should be made unambiguous.

## Spec compliance summary

| Area | Assessment | Notes |
|---|---|---|
| Agent-neutral state and mutation | Mostly compliant | Generic files, CLIs, and agent ID; no SDK coupling |
| Optional/simple path | Mostly compliant | Basic evidence/fact flow works without causal machinery |
| Adapter pluggability | Not compliant | Contract exists, discovery/manifest does not |
| Schema and referential integrity | Partially compliant | Basic IDs/bounds checked; status, correlation, finite LR, and resolution paths have gaps |
| Bayesian update | Partially compliant | Core odds update is deterministic; correlated negative evidence is mishandled |
| Human review triggers | Not compliant | Contradictions and threshold crossing do not follow the specified diversion semantics |
| Falsification checkpoint | Partially compliant | Gate exists; retry lifecycle leaves duplicate pending work |
| Lifecycle/current view | Not compliant | Target-side edges and new references to inactive nodes remain possible |
| Audit-first crash repair | Architecturally compliant | Correct direction, but full-history/full-record design will not scale |
| Urgency tiering | Partially compliant | Display-time tier only; no stored impact score; expensive and tie-prone |
| Cross-agent process delivery | Partially compliant | Neutral content in a Claude-specific, unpackaged location |

## Recommended order of work

1. Restore graph correctness: active-status checks/current-view semantics and
   propagation through both causal-edge endpoints.
2. Complete review resolution: contradiction decisions, replacement retention,
   and kind-specific validation before deleting queue items.
3. Harden Bayesian inputs and correlation semantics, including finite values
   and prior-edge correlation references.
4. Reconcile the two high-confidence triggers and make the falsification retry
   idempotent.
5. Add adapter discovery plus an agent-neutral process/CLI distribution layer.
6. Then optimize storage replay, grouped snapshot writes, urgency traversal,
   and codebase scanning before using the harness on large investigations.

