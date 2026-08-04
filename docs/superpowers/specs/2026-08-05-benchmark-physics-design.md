# Design: `benchmark-physics` — a lightweight physics-domain benchmark

Date: 2026-08-05
Status: approved for spec, not yet implemented

## Purpose

`benchmarks/pioneer` (on the `benchmark-pioneer` worktree/branch) tests the
causal-graph harness on SRE/microservice incident diagnosis: hidden evidence
must be searched for, and the harness's value shows up mainly in evidence
*selection*. This benchmark tests a different domain — quantum-transport
physics — using real bugs the author has already investigated by hand, so
gold answers are grounded in verified fact rather than authored fiction.

This is a **separate benchmark**, not a replacement for pioneer or for the
still-unbuilt social-science (`causal_judgement`) direction. All three are
independent, domain-specific probes of the same underlying harness.

## Location

New worktree/branch `benchmark-physics`, forked from current `master` (not
from `benchmark-pioneer`) so it starts with the `af071eb` pending-review fix
already in place — the stale-item bug documented in the pioneer shakedown
note does not need to be rediscovered here.

```
benchmarks/physics/
  cases/          # agent-visible: prompt + evidence (investigative track)
  gold/           # evaluator-only: root causes / chain / critical evidence
  control/        # agent-visible: standalone QA items (competence track)
  protocol.json   # frozen limits/fields/conditions, mirrors pioneer's shape
  benchmark.py    # read-only evidence broker + evaluator scoring
  README.md       # isolation boundary, what this can/cannot establish
  results/        # shakedown run write-ups
```

## Track 1: investigative cases (`cases/` + `gold/`)

Two cases, both drawn from real bugs documented in
`docs/experiments/2026-08-01-bare-vs-armed-agent-kitaev-vortex.md`. Case and
gold JSON follow pioneer's schema exactly: `cases/*.json` has
`id`/`title`/`difficulty`/`prompt`/`source_types`/`answer_contract`/`evidence[]`
(each evidence item: `id`/`source_type`/`component`/`timestamp`/`summary`/`content`/`tags`);
`gold/*.json` has `root_causes`/`required_chain`/`accepted_chain`/`critical_evidence_ids`.

Evidence content is **authored, self-contained reconstruction** of the real
investigation (derivations, doc/memo excerpts, code-snippet stand-ins, log
lines) — not a live pointer into the private target repository. Same
isolation principle as pioneer: nothing in `cases/` is fabricated fiction,
but nothing in it depends on external repo access either.

### `phys01` — `mu=0` counting-field broadening artifact

Prompt: is the reported "numerical instability" at `mu=0` in the Kitaev
chain counting-field method real, and what causes it.

Gold root cause: a systematic O(η) broadening artifact in the NEGF
current-conservation calculation, hugely amplified near the exact
zero-energy Majorana mode that exists throughout the Kitaev topological
phase — not a `mu=0`-specific bug. The counting-field/logdet path stays
exact regardless of η. Single, clean root cause; both the bare and armed
agents converged on it independently in the real run.

### `phys02` — vortex MZM authenticity

Prompt: at the historically-used parameter set
(`mu=0.6, Delta_0=0.2, xi_0=0.1, lambda_L=30, B=0, M=0`), are the observed
vortex-localized states genuine Majorana zero modes.

Gold root cause (required): the bulk is gapped and trivial at `B=0,M=0` —
the Bloch dispersion `d_z(k) = B*M + (4/3)cos(kx) - (1/3)cos(2kx) +
(4/3)cos(ky) - (1/3)cos(2ky)` never reaches zero at any TRIM point under
those parameters — so the near-zero states are not genuine MZMs; they come
from `mu` sitting just below the band edge. A nonzero mass term is needed
for a genuine gap closing.

Gold extension — `bonus_findings` (new field, not in pioneer's gold schema):
two additional real bugs found in the source investigation (vortex-position
collision from round-half-to-even landing both vortices on one lattice
site; `xi_0=0.1` saturating the pairing envelope so no room remains for a
localized Majorana wavefunction). These are scored as optional bonus
credit, not required for `joint_success` — the source investigation itself
left the boundary-condition question open, so gold must not force a false
consensus there. `score_answer` gains a `bonus_recall` field alongside the
existing required-chain scoring; it does not gate `joint_success`.

## Track 2: control items (`control/`)

Three items pulled from GPQA-diamond's physics category: standalone
multiple-choice questions, all information given inline, no search/read
step. Used only as an in-domain competence sanity check (can the model
reason correctly about this physics at all) — not a bare-vs-armed
comparison, since there is nothing for the harness to add when nothing is
hidden. Scoring is exact letter-match, no broker involved.

**Open risk, to resolve during implementation, not here:** GPQA is
distributed gated specifically to prevent its answer key leaking into
public training/eval corpora. Since this repo may be public, embedding
verbatim GPQA question text is a contamination/license risk. Before
authoring `control/`, verify GPQA's current usage terms permit this; if
not, substitute an equally well-accepted but openly reusable physics QA
source (e.g. a physics subset of an openly licensed MMLU-style set)
without changing anything else in this design.

## Harness (`benchmark.py`, `protocol.json`)

Copy-adapt pioneer's `benchmark.py` and `protocol.json` rather than
factoring out a shared module — avoids a refactor that isn't otherwise
motivated yet. Suite id `causal-graph-physics-v1`; same baseline/treatment
condition shape as pioneer (treatment adds `causal_graph_skill: true` +
`skill_path`); `runs_per_case_per_condition: 1`; same limits defaults
(`wall_time_seconds: 1200`, `search_calls: 12`, `evidence_reads: 12`,
`live_web: false`) unless a shakedown run shows they don't fit this
domain.

Known limitations inherited as-is from pioneer, not fixed here: exact-string
matching on root-cause/chain scoring, top-hypothesis-only scoring. Same
caveat as the pioneer shakedown note — this is a plumbing shakedown
benchmark first, not a scored comparison, until those are addressed
(tracked as pioneer's own open item, not duplicated here).

No model-provider runner ships in this repo, same as pioneer — running
against real models is external tooling.

## Explicit non-goals

- Not a replacement for pioneer or the social-science direction.
- Not fixing pioneer's scorer defects (exact-string matching, top-hypothesis
  only) — inherited, flagged, deferred.
- Not building a shared harness module across benchmarks yet.
- Not adding more than 2 investigative cases or 3 control items in this
  first pass — deliberately lightweight, matching the "shakedown before
  scale-up" lesson from the pioneer experiment.
