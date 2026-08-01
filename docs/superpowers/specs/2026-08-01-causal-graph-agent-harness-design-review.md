# Design Review: Causal Graph Agent Harness

Date: 2026-08-01  
Reviewed design: `2026-08-01-causal-graph-agent-harness-design.md`

## Verdict

The design is a good skeleton for an auditable hypothesis notebook: separating
evidence, claims, deterministic mutations, and agent instructions is sound.
It is not ready to be treated as an approved causal-reasoning or
confirmation-bias mitigation design, however. Four issues affect the validity
of its conclusions or its central auditability promise. They should be resolved
before implementing the full pipeline.

## 1. The mechanism that addresses the stated bias is deferred

The problem statement says the bias occurs during evidence selection and names
explicit falsification as the countermeasure (lines 9-14). The design then
makes the contrarian/falsification role a future non-goal (lines 37-40 and
211-215). The current process merely asks the same driving agent to run
"relevant" adapters, extract facts, and propose causes (lines 165-172).

That process does not change the evidence-selection behavior described in the
problem. An agent can select only confirming evidence and the harness will
faithfully turn it into a tidy graph and precise-looking posterior. Human review
and graph structure occur too late to reveal evidence that was never sought.
This means the first implementation would not solve the primary problem it is
being built to solve.

Required design change: a causal conclusion must pass a falsification
checkpoint before it can receive or cross a high-confidence status. This does
not require a separate debate agent in v1. The driving agent can be required to
(1) register at least one live alternative or an explicit "unknown" hypothesis,
(2) state an observation that would discriminate against the leading
hypothesis, (3) run and record a targeted counterevidence search, and (4) record
the search result, including a null result. The lightweight fact-only path can
remain exempt.

## 2. The numbers do not yet define a valid probabilistic causal model

A causal edge currently contains only endpoints and a `prior`/`posterior`
(lines 77-87 and 89-93). It does not define the probabilistic hypothesis being
updated, its negation or alternatives, the kind of causal relation, population
or time scope, or whether the claim is causal rather than merely temporal or
associational. Allowing arbitrary fact/deduction endpoint combinations makes
those ambiguities unavoidable.

In addition, sequentially multiplying agent-estimated likelihood ratios is
valid only when each ratio is conditional on all evidence already applied, or
when the evidence items are conditionally independent. The design specifies
neither and stores no evidence-dependency information (lines 105-109 and
170-172). Two reports derived from the same source, or two symptoms produced by
the same measurement, can therefore be counted twice. Deterministic arithmetic
will reproduce that error exactly; it does not make the resulting posterior
calibrated or trustworthy. The high-confidence review gate then gives those
unqualified numbers operational meaning.

Required design change: choose one of these paths before implementation:

- Treat the graph as a causal-*hypothesis* tracker and use ordinal support
  levels rather than Bayesian probabilities; or
- Define each edge as a scoped binary hypothesis with an explicit complement,
  typed relation, and interpretation. Store the basis and conditioning set for
  every likelihood ratio, track evidence provenance/dependency groups, reject
  reuse of the same evidence, and combine correlated evidence jointly rather
  than multiplying standalone estimates. Use posterior odds internally and do
  not allow exact 0/1 priors except for logical constraints.

Until one path is chosen, `posterior` and "high confidence" should not appear in
user-facing conclusions.

## 3. Revision preserves history but does not preserve correctness

The design says revisions mark facts or edges as superseded/contested without
overwriting them (lines 120-122), but the schemas contain no lifecycle/version
fields and the process defines no active-view or invalidation rules. If a fact
is retracted, deductions supported by it and causal posteriors updated from it
remain in place. A preserved audit trail is not enough: the harness also needs
an unambiguous answer to "what is currently believed, and why?"

This is especially damaging in a dependency graph because one correction may
invalidate a large derived subgraph. Merely putting the correction in a review
queue leaves stale conclusions available to subsequent agent steps.

Required design change: add immutable versions and explicit lifecycle state
(`active`, `contested`, `superseded`, `retracted`) with `supersedes_id` or an
equivalent relation. Define deterministic propagation: downstream deductions
and edge updates become `stale` when a dependency ceases to be active, are
excluded from the current view, and must be recomputed or explicitly reaffirmed.
Queue resolution must apply the status change and its invalidation set as one
operation. Add a test that retracts a root fact and verifies that no dependent
claim remains current.

## 4. Per-file atomic writes cannot provide the promised audit guarantee

Each mutation changes a graph JSON file and appends to `audit_log.jsonl`; some
also change `pending_review.jsonl` (lines 89-96 and 126-129). A temporary-file
rename is atomic for one file only. A crash after replacing graph state but
before appending the audit record creates an unaudited mutation; doing the
operations in the opposite order creates a phantom audit entry. The file lock
prevents concurrent writers but does not make a multi-file update atomic.
Consequently, the stated "no partial writes" guarantee (lines 238-246) is not
achievable with the described storage protocol.

Required design change: make one durable transaction record authoritative.
The simplest options are either SQLite with transactions/WAL, or an append-only
event journal with checksummed, uniquely identified, idempotent events from
which the JSON graph files are derived snapshots. The latter preserves the
inspectable/git-friendly files while making recovery deterministic. Tests must
inject failure at every write boundary and verify that recovery yields either
the complete mutation or none of it.

## Approval condition

Keep the adapter and CLI decomposition, but change the design status back to
draft until these four decisions are incorporated. The remaining details can
be refined during implementation; these four cannot, because they determine
whether the harness actually reduces confirmation bias, whether its numbers
mean anything, whether corrections propagate, and whether its audit history is
complete.
