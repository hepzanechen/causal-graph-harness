# Experiment: bare agent vs. causal-graph-armed agent, on real physics code

Date: 2026-08-01
Target project: a separate, private, in-progress quantum transport
simulation codebase (Kitaev chains, counting-field method, vortex MZMs)

This is the first real-world validation run of the causal graph agent harness
(`docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md`),
per the deferred-distribution plan in that spec's "Future work" section:
validate the skill's actual performance before investing further in
packaging/distribution.

## Method

For each challenge below, two fresh subagents were dispatched in parallel,
each with **zero memory of any prior conversation** (a new `Agent` tool
call, not a resumed session) — genuinely empty context, not just an
instruction to "pretend" not to know things.

- **Bare agent**: given only the project path and the question, told to
  diagnose (not fix) and report findings, using its own judgment.
- **Armed agent**: given the identical project path and question, plus one
  extra instruction — "read and follow this harness's `AGENTS.md` first."
  That's the harness's actual cross-agent entrance point; the armed agent
  had to discover installation and process from that file itself, the same
  way any other fresh agent dropped into this ecosystem would.

Both were constrained to diagnose-only (no edits to the target project) and
asked for the same report structure: reproduction status, root cause with
evidence, confidence + falsifiers, and files examined in order.

## Challenge 1: numerical instability at `mu=0` (Kitaev chain, counting-field method)

**Question posed:** "For the counting field method, it was previously
noticed that for the Kitaev model, when setting the chemical potential mu
to zero, there is numerical instability. Check whether this is real and
what causes it."

**Result: both agents converged on the same root cause**, independently:
the effect is real and reproducible, but it isn't true numerical
instability — it's a systematic, O(η) broadening artifact in the NEGF
current-conservation calculation, hugely amplified near the exact
zero-energy Majorana mode that exists throughout the Kitaev topological
phase (not something special to `mu=0` specifically; that's just the
conventional reference point). The counting-field/logdet path stays exact
regardless of η. Both explicitly ruled out a `mu==0`-specific code bug and
cross-referenced the project's own prior documentation (`memo.md`,
`doc/virtual-lab-log/observations.md`) acknowledging the general mechanism.

| | Bare | Armed |
|---|---|---|
| Tool calls | 41 | 60 |
| Wall time | ~4.1 min | ~5.3 min |
| Confidence stated | qualitative "high" | posterior **0.911** (prior 0.3 → 2 Bayesian updates) |

**The differentiator wasn't the conclusion — it was enforcement.** The
armed agent's first attempt to apply its second piece of evidence was
**mechanically blocked** by `update_causal_edge.py`: *"high-confidence
threshold crossed without a recorded falsification check."* Only after it
went and ran an actual counter-hypothesis search (checking for a
`mu==0`-specific code bug by scanning `mu` continuously for a
discontinuity — found none) did the script let the posterior cross 0.9.
This is a real, observed instance of the falsification gate firing, not a
hypothetical — verified directly in the graph's own
`falsification_checks[]` record, not just claimed in the agent's prose.

A useful bonus: the queue retained one stale, superseded pending item from
that diverted-then-retried update. That's exactly the scenario fixed
earlier this session (`resolve_pending.py`'s duplicate-evidence guard,
added after an independent code review found the gap). The armed agent
independently noticed the stale item and correctly explained why it's
harmless — a real field confirmation that fix holds under unscripted use.

Graph artifacts: `<target-project>/research/kitaev-mu0-instability/graph/`

## Challenge 2: are the vortex MZMs genuine? (`MZMVortexHamiltonian`)

**Question posed:** the author was unsure whether the vortices seen in the
vortex density-of-states results are genuine Majorana zero modes for the
parameters currently used, or whether the apparent MZM-like signal could
be a bug/artifact.

**Bottom line: both agreed — not a genuine MZM at the historically-used
parameters.** Both independently recovered essentially the same parameter
set from two *different* sources (bare: deleted `.mat` output filenames
via `git log --diff-filter=D`; armed: a notebook on the `main` branch) —
`mu=0.6, Delta_0=0.2, xi_0=0.1, lambda_L=30, B=0, M=0`. Both also
positively confirmed the code *can* produce genuine vortex-localized,
hybridizing MZMs once the mass term is switched on (a replicated positive
control).

**Where they diverged on mechanism** — and this is the more interesting
result of the two challenges:

- Bare agent: claimed the normal-state Hamiltonian is a **gapless** Dirac
  cone at `B=0` (mass term `B·M` vanishes), and that the near-zero states
  are **open-boundary corner artifacts** unrelated to the vortex (control
  test: the same state appears with no vortex/pairing/vector-potential at
  all).
- Armed agent: derived the full Bloch dispersion
  `d_z(k) = B·M + (4/3)cos(kx) − (1/3)cos(2kx) + (4/3)cos(ky) − (1/3)cos(2ky)`
  and found it's never zero at any TRIM point when `B=0,M=0` — the bulk is
  **fully gapped and trivial**, and the near-zero states come from `mu`
  sitting just below the band edge.

I independently re-derived `d_z(k)` by hand from the actual hopping
matrices in `Central.py:247-298` to arbitrate: **the armed agent's formula
and TRIM-point values check out exactly.** The bulk genuinely is gapped.
This doesn't necessarily make the bare agent's numerical finding wrong,
though — its source used the class's default `boundary_condition='open'`,
while the armed agent's source notebook explicitly used **periodic** BC
(plus a smaller system size, Nx=Ny=4 vs 10). A gapped bulk under open
boundaries can still host in-gap corner artifacts as a lattice-termination
effect, so the two explanations may both be locally correct about
*different* specific runs rather than actually contradicting each other.
**This is the one open thread from this experiment**: neither agent's
source pins down which boundary condition the author's actual
"vortex DOS" plot was generated with.

**Two additional, concrete, likely-real bugs — found only by the armed
agent**, surfaced specifically by its falsification check retesting at a
properly-tuned critical point rather than stopping at the first
explanation:
1. The two vortex positions (`round(N*0.45)+0.5`, `round(N*0.55)+0.5`)
   land on the identical lattice site for every even N (Python's
   round-half-to-even) — coded as two vortices, actually one point defect.
2. `xi_0=0.1` saturates the pairing envelope to >0.9999 by r=1, leaving no
   room for a Majorana wavefunction to localize into a vortex core —
   confirmed to persist even at the properly-tuned critical mass point.

**Findings only the bare agent surfaced**, via a different investigative
strategy (git archaeology rather than analytic derivation):
- Recovered the deleted original MATLAB reference implementation
  (`matlabCode/vortex/params.txt`) — the working prototype used
  `B=2, m=2`, i.e. the mass term was *intentionally* nonzero there.
- `MZMVortexHamiltonian`/`TopologicalSurface2D` are completely unused
  anywhere in the currently tracked codebase — not in `CATALOG`, no test
  coverage, no current script or example drives them.
- Found and correctly resolved a doc-vs-code discrepancy in the vector
  potential formula (concluded the code is right; the reference doc has a
  transcription artifact).

Graph artifacts: `<target-project>/research/vortex-dos-mzm-authenticity/graph/`

## Takeaways (n=2, same underlying model, no ground-truth oracle — read accordingly)

- **Challenge 1** was closer to a wash on "quality of conclusion" — the
  bare agent reasoned well on its own. The harness's value there was
  narrow but real: it *forced* a falsification check before allowing high
  confidence, mechanically, and left a durable structured artifact instead
  of only prose.
- **Challenge 2** showed more differentiated value: the armed agent's
  falsification-retry step is what surfaced the second compounding bug
  (the vortex core issue) — it didn't stop at the first plausible
  explanation because the process required actively trying to break it.
  The bare agent, in turn, found things the harness's process didn't
  prompt for at all (git archaeology into deleted history, orphaned-code
  detection) — a genuinely complementary style, not a strictly worse one.
- Having the armed run's claims as discrete, individually-evidenced facts
  (rather than one paragraph of prose) is what made it practical to
  independently re-derive and check the one disputed technical claim in a
  few minutes, instead of just weighing two summaries against each other.
- Two real bugs surfaced in the target project (vortex-position collision,
  undersized `xi_0`) remain unfixed, pending the author's confirmation of
  which historical run/boundary-condition they actually care about.
- This is still a 2-run sample against one codebase; not a basis for
  publishing the harness yet (see the design spec's deferred-distribution
  section) but a genuine, positive first data point.
