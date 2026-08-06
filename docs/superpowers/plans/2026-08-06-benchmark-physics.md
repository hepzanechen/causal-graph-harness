# benchmark-physics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `benchmark-physics` benchmark package (2 investigative cases + 3 control items + evidence broker + scorer), then run one bare-vs-armed shakedown against `opencode/deepseek-v4-flash`, mirroring the pioneer benchmark's method.

**Architecture:** A new worktree/branch `benchmark-physics`, forked from `master`, holding `benchmarks/physics/{cases,gold,control,results}/` plus a copy-adapted `benchmark.py` (read-only evidence broker + evaluator-only scorer) and `protocol.json`. Case content is authored from the real, already-diagnosed bugs in `docs/experiments/2026-08-01-bare-vs-armed-agent-kitaev-vortex.md`; control content is 3 items from MMLU's openly-licensed `college_physics` test set, fetched verbatim.

**Tech Stack:** Python 3.10+, stdlib only (json, pathlib, argparse), pytest for tests, `opencode` CLI for the shakedown run.

## Global Constraints

- Fork the worktree from `master`, not `benchmark-pioneer` — `master` already has the `af071eb` pending-review fix.
- Case/gold JSON schema is defined fresh in this plan (Task 1); it does not need to byte-match pioneer's undocumented internals, only be internally consistent with `benchmark.py`.
- Known scorer limitations (exact-string/concept-id matching, top-hypothesis-only scoring) are inherited as-is from pioneer — do not fix them in this plan.
- No model-provider runner ships as library code — the shakedown run (Task 9) is an external `opencode` CLI invocation, documented in `results/`, same as pioneer.
- Control items must come from an openly licensed source (MMLU), not GPQA — resolves the licensing risk flagged in the design spec.

---

### Task 1: Create the worktree and scaffold directories

**Files:**
- Create (directories only): `benchmarks/physics/cases/`, `benchmarks/physics/gold/`, `benchmarks/physics/control/`, `benchmarks/physics/results/`

**Interfaces:** None — this task produces no code, only the workspace and empty directories later tasks populate.

- [ ] **Step 1: Create the worktree**

```bash
cd /home/kt/zero
git worktree add -b benchmark-physics .worktrees/benchmark-physics master
```

- [ ] **Step 2: Verify the worktree**

Run: `git -C .worktrees/benchmark-physics status` and `git -C .worktrees/benchmark-physics log -1 --oneline`
Expected: clean working tree, HEAD matches current `master`'s tip commit.

All remaining tasks operate inside `.worktrees/benchmark-physics` (referred to below simply as the repo root).

- [ ] **Step 3: Scaffold directories**

```bash
cd /home/kt/zero/.worktrees/benchmark-physics
mkdir -p benchmarks/physics/cases benchmarks/physics/gold benchmarks/physics/control benchmarks/physics/results
```

- [ ] **Step 4: Commit the scaffold**

```bash
git add benchmarks/physics
git commit -m "Scaffold benchmark-physics directory structure" --allow-empty
```

(`--allow-empty` only needed if git doesn't track the empty dirs; if `git status` shows nothing staged, skip the commit here and let Task 2's `protocol.json` be the first real commit.)

---

### Task 2: Write `protocol.json`

**Files:**
- Create: `benchmarks/physics/protocol.json`

**Interfaces:**
- Produces: the frozen protocol all later tasks and the Task 9 shakedown read `case_ids`, `control_ids`, `conditions`, and `limits` from.

- [ ] **Step 1: Write the file**

```json
{
  "suite_id": "causal-graph-physics-v1",
  "case_ids": ["phys01", "phys02"],
  "control_ids": ["ctrl01", "ctrl02", "ctrl03"],
  "conditions": {
    "baseline": {
      "causal_graph_skill": false
    },
    "treatment": {
      "causal_graph_skill": true,
      "skill_path": "AGENTS.md"
    }
  },
  "runs_per_case_per_condition": 1,
  "limits": {
    "wall_time_seconds": 1200,
    "search_calls": 12,
    "evidence_reads": 12,
    "live_web": false
  },
  "shared_instruction": "You are diagnosing a physics simulation question. Use only the benchmark.py CLI (list/prompt/search/read) to gather evidence for cases, or list-control/control-prompt for control items. Do not access any files outside this benchmark's cases/control directories. Report your final answer as JSON matching the case's answer_contract (for cases) or {\"selected_answer\": \"<letter>\"} (for control items). Do not fabricate citations to evidence IDs you did not read.",
  "isolation": {
    "agent_visible": ["benchmarks/physics/cases", "benchmarks/physics/control", "benchmarks/physics/protocol.json", "benchmarks/physics/benchmark.py"],
    "evaluator_only": ["benchmarks/physics/gold"]
  },
  "record": ["condition", "case_id", "wall_time_seconds", "search_calls", "evidence_reads", "input_tokens", "output_tokens", "answer_json", "score"]
}
```

- [ ] **Step 2: Validate it's well-formed JSON**

Run: `python3 -c "import json; json.load(open('benchmarks/physics/protocol.json'))"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/physics/protocol.json
git commit -m "Add benchmark-physics protocol.json"
```

---

### Task 3: Author `phys01` case + gold (mu=0 broadening artifact)

**Files:**
- Create: `benchmarks/physics/cases/phys01.json`
- Create: `benchmarks/physics/gold/phys01.json`

**Interfaces:**
- Produces: the concept-id vocabulary `negf-current-uses-eta-regularization`, `error-scales-with-inverse-eta`, `zero-mode-present-throughout-topological-phase`, `error-amplified-near-zero-mode`, `negf-eta-broadening-artifact-near-zero-mode` — Task 6's tests reference these exact strings.

- [ ] **Step 1: Write the case file**

```json
{
  "id": "phys01",
  "title": "mu=0 numerical instability in the Kitaev chain counting-field method",
  "difficulty": "medium",
  "prompt": "For the counting-field method applied to a Kitaev chain, it was previously noticed that when the chemical potential mu is set exactly to zero, the current calculation shows numerical instability. Determine whether this is a real physical/numerical effect or a mu=0-specific code bug, and identify the root cause. Use search/read to gather evidence before answering.",
  "source_types": ["doc", "code", "metric"],
  "answer_contract": {
    "format": "json",
    "required_fields": ["hypotheses"],
    "hypothesis_fields": ["rank", "root_cause", "causal_chain", "confidence", "cited_evidence_ids"],
    "causal_chain_edge_fields": ["from", "to", "relation"]
  },
  "evidence": [
    {
      "id": "phys01-ev01",
      "source_type": "doc",
      "component": "memo.md",
      "timestamp": "2026-07-14T09:00:00Z",
      "summary": "Prior note acknowledging a general broadening-artifact mechanism near zero-energy modes for eta-regularized NEGF calculations.",
      "content": "memo.md, section 'Known numerical caveats': the NEGF current formula regularizes the retarded Green's function with a small imaginary broadening eta (G_R = (E - H + i*eta)^-1). This is known to introduce an O(eta) systematic error in the computed current whenever the spectrum has a state within ~eta of the reference energy. We have not yet quantified how large this effect is across our parameter range.",
      "tags": ["negf", "eta-regularization", "known-caveat"]
    },
    {
      "id": "phys01-ev02",
      "source_type": "doc",
      "component": "doc/virtual-lab-log/observations.md",
      "timestamp": "2026-07-20T14:30:00Z",
      "summary": "Lab log entry noting the mu=0 instability was first observed and flagged for follow-up, without root-causing it at the time.",
      "content": "doc/virtual-lab-log/observations.md, 2026-07-20: Running the current sweep at mu=0 for the Kitaev chain gives visibly noisier output than neighboring mu values; increasing eta smooths it out but changes the answer. Flagging for follow-up -- unclear if this is mu=0-specific or a broader issue we're only noticing here because mu=0 is our default reference point.",
      "tags": ["observation", "mu=0", "follow-up-needed"]
    },
    {
      "id": "phys01-ev03",
      "source_type": "code",
      "component": "negf_current.py:88-104",
      "timestamp": "2026-07-01T00:00:00Z",
      "summary": "NEGF current-conservation calculation code, showing the eta-regularized retarded Green's function used to compute the current.",
      "content": "negf_current.py:88-104\n\ndef compute_current(H, mu, eta=1e-3, ...):\n    G_R = np.linalg.inv((E - H - mu * I) + 1j * eta * I)\n    ...\n    current = _current_from_greens_function(G_R, ...)\n    return current\n\n# eta is a fixed regularization constant across all mu values; no\n# mu-dependent branching or special-casing exists anywhere in this function.",
      "tags": ["negf", "code", "eta"]
    },
    {
      "id": "phys01-ev04",
      "source_type": "code",
      "component": "counting_field.py:40-55",
      "timestamp": "2026-07-01T00:00:00Z",
      "summary": "Counting-field/logdet current calculation path, which does not use an eta regularization and is exact.",
      "content": "counting_field.py:40-55\n\ndef counting_field_current(H, mu, chi, ...):\n    # This path evaluates a log-determinant of a matrix built directly\n    # from H and the counting field chi; it never constructs a retarded\n    # Green's function and takes no eta parameter at all.\n    logdet = np.linalg.slogdet(_counting_field_matrix(H, mu, chi))[1]\n    return _current_from_logdet_derivative(logdet, chi)",
      "tags": ["counting-field", "code", "exact"]
    },
    {
      "id": "phys01-ev05",
      "source_type": "metric",
      "component": "sweep_results/current_error_vs_mu.csv",
      "timestamp": "2026-07-22T11:00:00Z",
      "summary": "A continuous sweep of |NEGF current - counting-field current| vs mu shows the error is large throughout the entire topological phase (|mu| < 2t), not only at mu=0.",
      "content": "sweep_results/current_error_vs_mu.csv (excerpt, t=1, eta=1e-3):\nmu=-1.8, error=0.041\nmu=-1.0, error=0.052\nmu=-0.4, error=0.061\nmu=0.0, error=0.058\nmu=0.4, error=0.055\nmu=1.0, error=0.049\nmu=1.8, error=0.038\nmu=2.2, error=0.0004   <- outside topological phase, error collapses\nmu=3.0, error=0.0001",
      "tags": ["sweep", "error-vs-mu", "topological-phase"]
    },
    {
      "id": "phys01-ev06",
      "source_type": "code",
      "component": "test_mu_continuity.py:12-30",
      "timestamp": "2026-07-23T16:00:00Z",
      "summary": "A control test scanning mu continuously through zero for any discontinuity in the NEGF code path; none found, ruling out a mu=0-specific code bug.",
      "content": "test_mu_continuity.py:12-30\n\ndef test_no_discontinuity_at_mu_zero():\n    mus = np.linspace(-0.01, 0.01, 2001)\n    currents = [compute_current(H, mu) for mu in mus]\n    diffs = np.diff(currents)\n    assert np.max(np.abs(diffs)) < 1e-6  # smooth through mu=0, no branch/discontinuity\n\n# Result: PASSED. No mu==0-specific branching exists; the function is\n# numerically smooth through mu=0 to the precision of this scan.",
      "tags": ["test", "control", "no-discontinuity"]
    }
  ]
}
```

- [ ] **Step 2: Write the gold file**

```json
{
  "case_id": "phys01",
  "root_causes": ["negf-eta-broadening-artifact-near-zero-mode"],
  "required_chain": [
    {"from": "negf-current-uses-eta-regularization", "to": "error-scales-with-inverse-eta", "relation": "contributes-to"},
    {"from": "zero-mode-present-throughout-topological-phase", "to": "error-amplified-near-zero-mode", "relation": "contributes-to"},
    {"from": "error-scales-with-inverse-eta", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"},
    {"from": "error-amplified-near-zero-mode", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"}
  ],
  "accepted_chain": [
    {"from": "negf-current-uses-eta-regularization", "to": "error-scales-with-inverse-eta", "relation": "contributes-to"},
    {"from": "zero-mode-present-throughout-topological-phase", "to": "error-amplified-near-zero-mode", "relation": "contributes-to"},
    {"from": "error-scales-with-inverse-eta", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"},
    {"from": "error-amplified-near-zero-mode", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"}
  ],
  "critical_evidence_ids": ["phys01-ev01", "phys01-ev03", "phys01-ev04", "phys01-ev05", "phys01-ev06"],
  "not_root_cause": ["mu-equals-zero-specific-code-bug"]
}
```

`accepted_chain` is identical to `required_chain` here — there is one clean, single-mechanism causal path in this case, unlike `phys02`.

- [ ] **Step 3: Validate both files parse**

Run: `python3 -c "import json; json.load(open('benchmarks/physics/cases/phys01.json')); json.load(open('benchmarks/physics/gold/phys01.json'))"`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/physics/cases/phys01.json benchmarks/physics/gold/phys01.json
git commit -m "Add phys01 case: mu=0 NEGF broadening artifact"
```

---

### Task 4: Author `phys02` case + gold (vortex MZM authenticity)

**Files:**
- Create: `benchmarks/physics/cases/phys02.json`
- Create: `benchmarks/physics/gold/phys02.json`

**Interfaces:**
- Produces: concept ids `bloch-dispersion-nonzero-at-trim-points`, `bulk-gapped-and-trivial-at-B0-M0`, `mu-sits-just-below-band-edge`, `near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk`, plus the `bonus_findings` field (new relative to pioneer's gold schema) with entries `vortex-position-collision` and `xi0-saturation` — Task 6's tests and `score_answer`'s `bonus_recall` logic reference these exact ids.

- [ ] **Step 1: Write the case file**

```json
{
  "id": "phys02",
  "title": "Are the vortex-localized states genuine Majorana zero modes?",
  "difficulty": "hard",
  "prompt": "At the historically-used parameter set (mu=0.6, Delta_0=0.2, xi_0=0.1, lambda_L=30, B=0, M=0), the vortex density-of-states results show near-zero-energy states localized at the vortex cores. Determine whether these are genuine Majorana zero modes for these parameters, or an artifact, and identify the root cause. Use search/read to gather evidence before answering.",
  "source_types": ["doc", "code", "metric"],
  "answer_contract": {
    "format": "json",
    "required_fields": ["hypotheses"],
    "hypothesis_fields": ["rank", "root_cause", "causal_chain", "confidence", "cited_evidence_ids", "bonus_findings"],
    "causal_chain_edge_fields": ["from", "to", "relation"]
  },
  "evidence": [
    {
      "id": "phys02-ev01",
      "source_type": "doc",
      "component": "notebook: vortex_dos_run.ipynb, cell 3",
      "timestamp": "2026-07-10T08:00:00Z",
      "summary": "The historically-used parameter set for the vortex DOS plot.",
      "content": "vortex_dos_run.ipynb, cell 3:\nparams = dict(mu=0.6, Delta_0=0.2, xi_0=0.1, lambda_L=30, B=0, M=0)\nham = MZMVortexHamiltonian(**params)\nplot_vortex_dos(ham)",
      "tags": ["parameters", "historical-run"]
    },
    {
      "id": "phys02-ev02",
      "source_type": "code",
      "component": "Central.py:247-298",
      "timestamp": "2026-06-15T00:00:00Z",
      "summary": "Hopping-matrix construction for the normal-state Bloch Hamiltonian, from which d_z(k) can be derived.",
      "content": "Central.py:247-298\n\ndef normal_state_hopping(kx, ky, B, M, t=1.0):\n    # Nearest and next-nearest neighbor hopping on the square lattice,\n    # plus a Zeeman-like mass term B*M.\n    dz = B * M + (4/3) * np.cos(kx) - (1/3) * np.cos(2*kx) \\\n              + (4/3) * np.cos(ky) - (1/3) * np.cos(2*ky)\n    return dz",
      "tags": ["hamiltonian", "bloch", "code"]
    },
    {
      "id": "phys02-ev03",
      "source_type": "metric",
      "component": "trim_point_scan.csv",
      "timestamp": "2026-07-25T10:00:00Z",
      "summary": "Evaluation of d_z(k) at all four TRIM points (k in {0,pi}^2) with B=0, M=0, showing it is never zero -- the bulk gap does not close.",
      "content": "trim_point_scan.csv (B=0, M=0):\n(kx,ky)=(0,0):     dz=2.000\n(kx,ky)=(0,pi):    dz=0.667\n(kx,ky)=(pi,0):    dz=0.667\n(kx,ky)=(pi,pi):   dz=-0.667\nMinimum |dz| across full BZ (dense scan): 0.667 -- strictly nonzero, bulk is gapped.",
      "tags": ["trim-points", "bulk-gap", "B=0,M=0"]
    },
    {
      "id": "phys02-ev04",
      "source_type": "doc",
      "component": "doc/virtual-lab-log/observations.md",
      "timestamp": "2026-07-26T09:00:00Z",
      "summary": "Note that mu=0.6 sits just below the band edge implied by the B=0,M=0 gapped dispersion, which is offered as the source of the near-zero in-gap-looking states.",
      "content": "doc/virtual-lab-log/observations.md, 2026-07-26: with B=0,M=0 the bulk band edge (minimum quasiparticle energy away from the vortex) works out close to mu=0.6 once xi_0 and Delta_0 are folded in -- the near-zero states we're seeing are consistent with mu sitting just below that edge, not with an actual bulk gap closing.",
      "tags": ["band-edge", "mu", "near-zero-states"]
    },
    {
      "id": "phys02-ev05",
      "source_type": "code",
      "component": "vortex_setup.py:18-24",
      "timestamp": "2026-06-20T00:00:00Z",
      "summary": "Vortex position calculation, showing both vortex positions computed via round() on N*0.45+0.5 and N*0.55+0.5.",
      "content": "vortex_setup.py:18-24\n\ndef vortex_positions(N):\n    v1 = round(N * 0.45) + 0.5\n    v2 = round(N * 0.55) + 0.5\n    return v1, v2\n\n# For N=10 (even): round(4.5)=4 (Python round-half-to-even), round(5.5)=6\n# -> v1=4.5, v2=6.5. But for many even N, round(N*0.45) and\n# round(N*0.55) land on the SAME integer under round-half-to-even,\n# producing v1 == v2 (a single point defect, not two vortices).",
      "tags": ["vortex-position", "code", "round-half-to-even"]
    },
    {
      "id": "phys02-ev06",
      "source_type": "metric",
      "component": "pairing_envelope_profile.csv",
      "timestamp": "2026-07-27T12:00:00Z",
      "summary": "The pairing envelope as a function of radial distance r from the vortex core, showing it saturates above 0.9999 by r=1 for xi_0=0.1.",
      "content": "pairing_envelope_profile.csv (xi_0=0.1):\nr=0.0, envelope=0.0000\nr=0.5, envelope=0.9817\nr=1.0, envelope=0.9999\nr=1.5, envelope=1.0000\nr=2.0, envelope=1.0000\n# The envelope saturates within one lattice site of the vortex core,\n# leaving essentially no spatial room for a localized Majorana\n# wavefunction to build up inside the core.",
      "tags": ["xi_0", "pairing-envelope", "saturation"]
    },
    {
      "id": "phys02-ev07",
      "source_type": "doc",
      "component": "notebook: mass_term_control.ipynb, cell 5",
      "timestamp": "2026-07-28T15:00:00Z",
      "summary": "Positive control: switching on a nonzero mass term (B,M != 0) does produce genuine vortex-localized, hybridizing MZMs.",
      "content": "mass_term_control.ipynb, cell 5: with B=2, M=2 (mass term on), the bulk gap closes and reopens with an inverted sign, and the vortex DOS shows two localized near-zero states that hybridize and split as vortex separation is varied -- consistent with genuine MZM behavior. This confirms the code CAN produce real MZMs; the question is only whether the historical B=0,M=0 run does.",
      "tags": ["control", "mass-term", "genuine-mzm"]
    }
  ]
}
```

- [ ] **Step 2: Write the gold file**

```json
{
  "case_id": "phys02",
  "root_causes": ["near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk"],
  "required_chain": [
    {"from": "bloch-dispersion-nonzero-at-trim-points", "to": "bulk-gapped-and-trivial-at-B0-M0", "relation": "implies"},
    {"from": "bulk-gapped-and-trivial-at-B0-M0", "to": "near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk", "relation": "causes"},
    {"from": "mu-sits-just-below-band-edge", "to": "near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk", "relation": "contributes-to"}
  ],
  "accepted_chain": [
    {"from": "bloch-dispersion-nonzero-at-trim-points", "to": "bulk-gapped-and-trivial-at-B0-M0", "relation": "implies"},
    {"from": "bulk-gapped-and-trivial-at-B0-M0", "to": "near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk", "relation": "causes"},
    {"from": "mu-sits-just-below-band-edge", "to": "near-zero-states-are-not-genuine-mzm-due-to-trivial-gapped-bulk", "relation": "contributes-to"}
  ],
  "critical_evidence_ids": ["phys02-ev01", "phys02-ev02", "phys02-ev03", "phys02-ev04", "phys02-ev07"],
  "bonus_findings": [
    {
      "id": "vortex-position-collision",
      "concept_id": "vortex-positions-collide-round-half-to-even",
      "description": "The two vortex positions round(N*0.45)+0.5 and round(N*0.55)+0.5 land on the identical lattice site for many even N due to Python's round-half-to-even, producing one point defect instead of two vortices.",
      "supporting_evidence_ids": ["phys02-ev05"]
    },
    {
      "id": "xi0-saturation",
      "concept_id": "xi0-pairing-envelope-saturates-blocking-localization",
      "description": "xi_0=0.1 saturates the pairing envelope to over 0.9999 by r=1, leaving no room for a Majorana wavefunction to localize into a vortex core.",
      "supporting_evidence_ids": ["phys02-ev06"]
    }
  ],
  "not_root_cause": ["gapless-dirac-cone-at-B0"]
}
```

- [ ] **Step 3: Validate both files parse**

Run: `python3 -c "import json; json.load(open('benchmarks/physics/cases/phys02.json')); json.load(open('benchmarks/physics/gold/phys02.json'))"`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/physics/cases/phys02.json benchmarks/physics/gold/phys02.json
git commit -m "Add phys02 case: vortex MZM authenticity"
```

---

### Task 5: Author control items from MMLU `college_physics`

**Files:**
- Create: `benchmarks/physics/control/ctrl01.json`, `ctrl02.json`, `ctrl03.json`

**Interfaces:**
- Produces: 3 files each with fields `id`, `question`, `choices` (dict with keys `A`,`B`,`C`,`D`), `correct_answer` (one of those letters, evaluator-only — lives in the same file since these are single-fact QA items, not investigations; Task 6's `load_control` must strip `correct_answer` before returning to the agent, same isolation principle as `gold/` for cases), `source`, `source_url`, `license`.

- [ ] **Step 1: Fetch real MMLU `college_physics` test items**

Use the WebFetch tool (or `curl`, if network access is available in this environment) to retrieve:
`https://raw.githubusercontent.com/hendrycks/test/master/data/test/college_physics_test.csv`

MMLU is MIT-licensed (see `https://github.com/hendrycks/test/blob/master/LICENSE`) — openly reusable, resolving the licensing risk flagged in the design spec (GPQA is gated specifically against this kind of reuse; MMLU is not).

Pick 3 items from the fetched CSV (e.g. rows 1, 15, 30 — any three is fine, no special selection criterion needed for a lightweight shakedown). Each MMLU row is `question,A,B,C,D,answer_letter`.

- [ ] **Step 2: Write the 3 control files**

For each of the 3 chosen rows, write a file shaped like this (using the actual fetched question/choices/answer — do not invent physics content; copy verbatim from the CSV row):

```json
{
  "id": "ctrl01",
  "question": "<verbatim question text from the fetched CSV row>",
  "choices": {
    "A": "<verbatim choice A>",
    "B": "<verbatim choice B>",
    "C": "<verbatim choice C>",
    "D": "<verbatim choice D>"
  },
  "correct_answer": "<verbatim answer letter from the CSV row>",
  "source": "MMLU college_physics test set",
  "source_url": "https://github.com/hendrycks/test",
  "license": "MIT"
}
```

Repeat for `ctrl02.json` and `ctrl03.json` with the other two chosen rows.

- [ ] **Step 3: Validate all three parse and have exactly 4 choices + a valid answer letter**

Run:
```bash
python3 -c "
import json
for f in ['ctrl01','ctrl02','ctrl03']:
    d = json.load(open(f'benchmarks/physics/control/{f}.json'))
    assert set(d['choices'].keys()) == {'A','B','C','D'}, f
    assert d['correct_answer'] in d['choices'], f
print('ok')
"
```
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/physics/control/
git commit -m "Add 3 control items from MMLU college_physics"
```

---

### Task 6: Write `benchmark.py` with tests (TDD)

**Files:**
- Create: `benchmarks/physics/benchmark.py`
- Test: `tests/test_physics_benchmark.py`

**Interfaces:**
- Consumes: the JSON files from Tasks 2-5 (`protocol.json`, `cases/*.json`, `gold/*.json`, `control/*.json`).
- Produces (for Task 9's shakedown run and any future caller):
  - `BenchmarkError(Exception)`
  - `list_cases() -> list[str]`
  - `load_case(case_id: str) -> dict` (case content only, no gold)
  - `search_evidence(case_id: str, query: str, limit: int = 5) -> list[dict]` (raises `BenchmarkError` on empty query or `limit` outside 1-10)
  - `read_evidence(case_id: str, evidence_id: str) -> dict` (full evidence item; raises `BenchmarkError` if unknown)
  - `score_answer(case_id: str, answer: dict) -> dict` with keys `root_match: bool`, `chain_recall: float`, `evidence_recall: float`, `bonus_recall: float | None`, `unsupported_edges: list`, `unknown_citations: list`, `joint_success: bool`
  - `list_control() -> list[str]`
  - `load_control(control_id: str) -> dict` (question + choices only, no `correct_answer`)
  - `score_control(control_id: str, selected_answer: str) -> dict` with key `correct: bool`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_physics_benchmark.py
import json
import sys
from pathlib import Path

import pytest

BENCH_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "physics"
sys.path.insert(0, str(BENCH_DIR))

import benchmark  # noqa: E402


def test_list_cases():
    assert benchmark.list_cases() == ["phys01", "phys02"]


def test_load_case_has_no_gold_fields():
    case = benchmark.load_case("phys01")
    assert case["id"] == "phys01"
    assert "root_causes" not in case
    assert "required_chain" not in case


def test_search_evidence_rejects_empty_query():
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.search_evidence("phys01", "")


def test_search_evidence_rejects_bad_limit():
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.search_evidence("phys01", "eta", limit=0)
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.search_evidence("phys01", "eta", limit=11)


def test_search_evidence_finds_relevant_item():
    results = benchmark.search_evidence("phys01", "eta regularization broadening")
    ids = {r["id"] for r in results}
    assert "phys01-ev01" in ids or "phys01-ev03" in ids


def test_read_evidence_returns_full_content():
    item = benchmark.read_evidence("phys01", "phys01-ev04")
    assert "logdet" in item["content"]


def test_read_evidence_unknown_id_raises():
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.read_evidence("phys01", "phys01-ev99")


def _correct_phys01_answer():
    return {
        "hypotheses": [
            {
                "rank": 1,
                "root_cause": "negf-eta-broadening-artifact-near-zero-mode",
                "causal_chain": [
                    {"from": "negf-current-uses-eta-regularization", "to": "error-scales-with-inverse-eta", "relation": "contributes-to"},
                    {"from": "zero-mode-present-throughout-topological-phase", "to": "error-amplified-near-zero-mode", "relation": "contributes-to"},
                    {"from": "error-scales-with-inverse-eta", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"},
                    {"from": "error-amplified-near-zero-mode", "to": "negf-eta-broadening-artifact-near-zero-mode", "relation": "causes"}
                ],
                "confidence": 0.9,
                "cited_evidence_ids": ["phys01-ev01", "phys01-ev03", "phys01-ev04", "phys01-ev05", "phys01-ev06"]
            }
        ]
    }


def test_score_answer_correct_yields_joint_success():
    result = benchmark.score_answer("phys01", _correct_phys01_answer())
    assert result["root_match"] is True
    assert result["chain_recall"] == 1.0
    assert result["joint_success"] is True


def test_score_answer_wrong_root_cause_fails():
    answer = _correct_phys01_answer()
    answer["hypotheses"][0]["root_cause"] = "mu-equals-zero-specific-code-bug"
    result = benchmark.score_answer("phys01", answer)
    assert result["root_match"] is False
    assert result["joint_success"] is False


def test_score_answer_unknown_citation_flagged():
    answer = _correct_phys01_answer()
    answer["hypotheses"][0]["cited_evidence_ids"].append("phys01-ev99")
    result = benchmark.score_answer("phys01", answer)
    assert "phys01-ev99" in result["unknown_citations"]
    assert result["joint_success"] is False


def test_list_control():
    assert benchmark.list_control() == ["ctrl01", "ctrl02", "ctrl03"]


def test_load_control_hides_answer():
    item = benchmark.load_control("ctrl01")
    assert "correct_answer" not in item
    assert set(item["choices"].keys()) == {"A", "B", "C", "D"}


def test_score_control():
    item_gold = json.loads((BENCH_DIR / "control" / "ctrl01.json").read_text())
    correct = item_gold["correct_answer"]
    wrong = next(l for l in "ABCD" if l != correct)
    assert benchmark.score_control("ctrl01", correct)["correct"] is True
    assert benchmark.score_control("ctrl01", wrong)["correct"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONNOUSERSITE= python3 -m pytest tests/test_physics_benchmark.py -v`
Expected: collection error or `ModuleNotFoundError: No module named 'benchmark'` — `benchmark.py` doesn't exist yet.

- [ ] **Step 3: Implement `benchmark.py`**

```python
# benchmarks/physics/benchmark.py
from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "cases"
GOLD_DIR = BASE_DIR / "gold"
CONTROL_DIR = BASE_DIR / "control"


class BenchmarkError(Exception):
    pass


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise BenchmarkError(f"not found: {path.name}")
    return json.loads(path.read_text())


def list_cases() -> list[str]:
    return sorted(p.stem for p in CASES_DIR.glob("*.json"))


def load_case(case_id: str) -> dict:
    return _load_json(CASES_DIR / f"{case_id}.json")


def _evidence_text(item: dict) -> str:
    return " ".join([item.get("summary", ""), item.get("content", ""), " ".join(item.get("tags", []))])


def search_evidence(case_id: str, query: str, limit: int = 5) -> list[dict]:
    terms = [t for t in _normalize(query).split("-") if t]
    if not terms:
        raise BenchmarkError("query must contain at least one search term")
    if not (1 <= limit <= 10):
        raise BenchmarkError("limit must be between 1 and 10")
    case = load_case(case_id)
    scored = []
    for item in case["evidence"]:
        haystack = _normalize(_evidence_text(item))
        score = sum(1 for t in terms if t in haystack)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    return [
        {"id": item["id"], "source_type": item["source_type"], "component": item["component"], "summary": item["summary"]}
        for _, item in scored[:limit]
    ]


def read_evidence(case_id: str, evidence_id: str) -> dict:
    case = load_case(case_id)
    for item in case["evidence"]:
        if item["id"] == evidence_id:
            return item
    raise BenchmarkError(f"unknown evidence id: {evidence_id}")


def _concept_set(ids: list[str]) -> set[str]:
    return {_normalize(i) for i in ids}


def _edge_set(chain: list[dict]) -> set[tuple[str, str, str]]:
    return {(_normalize(e["from"]), _normalize(e["to"]), _normalize(e["relation"])) for e in chain}


def score_answer(case_id: str, answer: dict) -> dict:
    gold = _load_json(GOLD_DIR / f"{case_id}.json")
    case = load_case(case_id)
    known_evidence_ids = {item["id"] for item in case["evidence"]}

    hypotheses = answer.get("hypotheses", [])
    if not hypotheses:
        raise BenchmarkError("answer has no hypotheses")
    top = min(hypotheses, key=lambda h: h.get("rank", 10**9))

    root_match = _concept_set([top.get("root_cause", "")]) == _concept_set(gold["root_causes"])

    predicted_edges = _edge_set(top.get("causal_chain", []))
    required_edges = _edge_set(gold["required_chain"])
    accepted_edges = _edge_set(gold["accepted_chain"])
    chain_recall = len(predicted_edges & required_edges) / len(required_edges) if required_edges else 1.0
    unsupported_edges = [e for e in predicted_edges if e not in accepted_edges]

    cited = top.get("cited_evidence_ids", [])
    unknown_citations = [c for c in cited if c not in known_evidence_ids]
    critical_ids = set(gold["critical_evidence_ids"])
    evidence_recall = len(critical_ids & set(cited)) / len(critical_ids) if critical_ids else 1.0

    bonus_recall = None
    if "bonus_findings" in gold:
        all_root_causes = _concept_set([h.get("root_cause", "") for h in hypotheses])
        all_cited_bonus_ids = set()
        for h in hypotheses:
            for bf in h.get("bonus_findings", []):
                all_cited_bonus_ids.add(_normalize(bf))
        bonus_concepts = _concept_set([bf["concept_id"] for bf in gold["bonus_findings"]])
        found = bonus_concepts & (all_root_causes | all_cited_bonus_ids)
        bonus_recall = len(found) / len(bonus_concepts) if bonus_concepts else 0.0

    joint_success = (
        root_match
        and chain_recall == 1.0
        and not unsupported_edges
        and not unknown_citations
    )

    return {
        "root_match": root_match,
        "chain_recall": chain_recall,
        "evidence_recall": evidence_recall,
        "bonus_recall": bonus_recall,
        "unsupported_edges": unsupported_edges,
        "unknown_citations": unknown_citations,
        "joint_success": joint_success,
    }


def list_control() -> list[str]:
    return sorted(p.stem for p in CONTROL_DIR.glob("*.json"))


def load_control(control_id: str) -> dict:
    item = _load_json(CONTROL_DIR / f"{control_id}.json")
    return {k: v for k, v in item.items() if k != "correct_answer"}


def score_control(control_id: str, selected_answer: str) -> dict:
    item = _load_json(CONTROL_DIR / f"{control_id}.json")
    return {"correct": selected_answer.strip().upper() == item["correct_answer"]}


def _cli_main(argv=None):
    import argparse
    import sys as _sys

    parser = argparse.ArgumentParser(prog="benchmark.py")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    p_prompt = sub.add_parser("prompt")
    p_prompt.add_argument("case_id")

    p_search = sub.add_parser("search")
    p_search.add_argument("case_id")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)

    p_read = sub.add_parser("read")
    p_read.add_argument("case_id")
    p_read.add_argument("evidence_id")

    p_score = sub.add_parser("score")
    p_score.add_argument("case_id")
    p_score.add_argument("answer_json_path")

    sub.add_parser("list-control")

    p_cprompt = sub.add_parser("control-prompt")
    p_cprompt.add_argument("control_id")

    p_cscore = sub.add_parser("score-control")
    p_cscore.add_argument("control_id")
    p_cscore.add_argument("selected_answer")

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            print(json.dumps(list_cases()))
        elif args.command == "prompt":
            print(json.dumps(load_case(args.case_id)))
        elif args.command == "search":
            print(json.dumps(search_evidence(args.case_id, args.query, args.limit)))
        elif args.command == "read":
            print(json.dumps(read_evidence(args.case_id, args.evidence_id)))
        elif args.command == "score":
            answer = json.loads(Path(args.answer_json_path).read_text())
            print(json.dumps(score_answer(args.case_id, answer)))
        elif args.command == "list-control":
            print(json.dumps(list_control()))
        elif args.command == "control-prompt":
            print(json.dumps(load_control(args.control_id)))
        elif args.command == "score-control":
            print(json.dumps(score_control(args.control_id, args.selected_answer)))
    except BenchmarkError as e:
        print(f"error: {e}", file=_sys.stderr)
        _sys.exit(1)


if __name__ == "__main__":
    _cli_main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONNOUSERSITE= python3 -m pytest tests/test_physics_benchmark.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/physics/benchmark.py tests/test_physics_benchmark.py
git commit -m "Add benchmark.py evidence broker and scorer, with tests"
```

---

### Task 7: Write `README.md`

**Files:**
- Create: `benchmarks/physics/README.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Write the file**

```markdown
# benchmark-physics

A lightweight physics-domain benchmark for the causal-graph agent harness.
See `docs/superpowers/specs/2026-08-05-benchmark-physics-design.md` for the
full design rationale.

## Isolation boundary

- Agent-visible: `cases/`, `control/`, `protocol.json`, `benchmark.py`.
- Evaluator-only, never shown to the agent: `gold/`. The `correct_answer`
  field inside each `control/*.json` file is also evaluator-only —
  `benchmark.py load_control` strips it before returning to a caller.

## Two tracks

- `cases/` (`phys01`, `phys02`) — investigative, hidden-evidence-broker
  cases grounded in real, already-diagnosed bugs from
  `docs/experiments/2026-08-01-bare-vs-armed-agent-kitaev-vortex.md`. Use
  `benchmark.py list|prompt|search|read|score`.
- `control/` (`ctrl01`-`ctrl03`) — standalone MMLU `college_physics`
  multiple-choice items, all information given inline, used only as an
  in-domain competence sanity check. Use
  `benchmark.py list-control|control-prompt|score-control`.

## What this can and cannot establish

Same caveat as `benchmark-pioneer`: this is a plumbing shakedown at n=1
per condition, not a scored statistical comparison. It inherits pioneer's
known scorer limitations (exact-concept-id matching, top-hypothesis-only
scoring) unmodified — see the design spec's non-goals.

## Running

No model-provider runner ships here — point an external agent (e.g. the
`opencode` CLI) at this directory and have it drive `benchmark.py` as its
only tool for interacting with `cases/`/`control/`. See `results/` for
past shakedown write-ups and the exact invocation used.
```

- [ ] **Step 2: Commit**

```bash
git add benchmarks/physics/README.md
git commit -m "Add benchmark-physics README"
```

---

### Task 8: Prepare prompts for the OpenCode shakedown

**Files:**
- Create: `benchmarks/physics/results/prompt_bare.txt`, `prompt_armed.txt`, `prompt_bare_phys02.txt`, `prompt_armed_phys02.txt`

**Interfaces:** None — these are run inputs, consumed only by Task 9.

Confirmed invocation (checked directly against the installed `opencode`
1.14.41 in this environment — `opencode --help` / `opencode run --help`):

```bash
opencode run "<message>" -m opencode/deepseek-v4-flash --dir <worktree-path> --format json --title <title>
```

`opencode/deepseek-v4-flash` is confirmed present in `opencode models`
output. `--dir` scopes the run to the given project path; since
`benchmarks/physics/` and `AGENTS.md` both live inside
`.worktrees/benchmark-physics`, there is no cross-boundary path for
OpenCode's `external_directory` permission gate to trip on this time
(unlike pioneer's shakedown, which referenced an `AGENTS.md` outside the
directory it ran in) — no separate permission-policy file is needed. If a
permission prompt fires anyway during Task 9 Step 1, fall back to
`--dangerously-skip-permissions` only for that run, and note it happened
in the results doc.

- [ ] **Step 1: Draft the two condition prompts as separate files (avoids the backtick/shell-quoting confound pioneer's shakedown hit)**

```bash
cat > benchmarks/physics/results/prompt_bare.txt <<'EOF'
You are investigating a physics diagnosis question using only the CLI at
benchmarks/physics/benchmark.py in this repo. Run 'python3
benchmarks/physics/benchmark.py list' to see available cases, then
'prompt <case_id>' to read the question, then 'search'/'read' to gather
evidence. Diagnose case phys01. Report your final answer as JSON matching
the case's answer_contract. Do not read any files outside
benchmarks/physics/.
EOF

cat > benchmarks/physics/results/prompt_armed.txt <<'EOF'
You are investigating a physics diagnosis question using only the CLI at
benchmarks/physics/benchmark.py in this repo. First read and follow
AGENTS.md. Run 'python3 benchmarks/physics/benchmark.py list' to see
available cases, then 'prompt <case_id>' to read the question, then
'search'/'read' to gather evidence. Diagnose case phys01. Report your
final answer as JSON matching the case's answer_contract. Do not read any
files outside benchmarks/physics/ and AGENTS.md.
EOF
```

Duplicate both files with `phys02` in place of `phys01` for the second case (`prompt_bare_phys02.txt`, `prompt_armed_phys02.txt`).

- [ ] **Step 2: Commit**

```bash
git add benchmarks/physics/results/prompt_bare.txt benchmarks/physics/results/prompt_armed.txt benchmarks/physics/results/prompt_bare_phys02.txt benchmarks/physics/results/prompt_armed_phys02.txt
git commit -m "Add benchmark-physics shakedown prompts"
```

---

### Task 9: Run the shakedown and write the results doc

**Files:**
- Create: `benchmarks/physics/results/2026-08-06-deepseek-v4-flash-shakedown.md`

**Interfaces:** None — this is the terminal task; it consumes everything built in Tasks 1-8 and produces a human-readable report, same shape as `benchmarks/pioneer/results/2026-08-01-deepseek-v4-flash-shakedown.md`.

- [ ] **Step 1: Run all 4 investigative-case conditions**

From the worktree root (`/home/kt/zero/.worktrees/benchmark-physics`), run each of the 4 combinations, capturing each command's stdout to its own file for later inspection (session ID, token/step counts, and the agent's final answer are all recoverable from the `--format json` event stream):

```bash
opencode run "$(cat benchmarks/physics/results/prompt_bare.txt)" -m opencode/deepseek-v4-flash --dir "$(pwd)" --format json --title phys01-bare > benchmarks/physics/results/run_phys01_bare.json
opencode run "$(cat benchmarks/physics/results/prompt_armed.txt)" -m opencode/deepseek-v4-flash --dir "$(pwd)" --format json --title phys01-armed > benchmarks/physics/results/run_phys01_armed.json
opencode run "$(cat benchmarks/physics/results/prompt_bare_phys02.txt)" -m opencode/deepseek-v4-flash --dir "$(pwd)" --format json --title phys02-bare > benchmarks/physics/results/run_phys02_bare.json
opencode run "$(cat benchmarks/physics/results/prompt_armed_phys02.txt)" -m opencode/deepseek-v4-flash --dir "$(pwd)" --format json --title phys02-armed > benchmarks/physics/results/run_phys02_armed.json
```

Each is a fresh session (no `--continue`/`--session` flag), so there is no shared context between the 4 runs. If OpenCode raises a permission prompt for any of them (unexpected given `--dir` already covers everything these prompts touch), rerun just that one with `--dangerously-skip-permissions` appended and note it in the results doc.

- [ ] **Step 2: Run the 3 control items in both conditions**

Same pattern, one `opencode run` per (control item x condition) pointed at `benchmark.py control-prompt <id>` instead of `prompt <id>` in the message text — since control items have no hidden evidence, this mainly checks the harness overhead doesn't corrupt a simple answer, not a meaningful bare-vs-armed split. 6 runs total (3 items x 2 conditions), same capture-to-file pattern as Step 1.

- [ ] **Step 3: Score every run**

For each investigative run, write the agent's final JSON answer to a temp file and run:
```bash
python3 benchmarks/physics/benchmark.py score phys01 /path/to/answer.json
```
For each control run:
```bash
python3 benchmarks/physics/benchmark.py score-control ctrl01 <letter>
```

- [ ] **Step 4: Write the results doc**

Follow the structure of `benchmarks/pioneer/results/2026-08-01-deepseek-v4-flash-shakedown.md`: verdict summary, a per-case pass/fail table (bare vs armed), a cost/steps table if token/step counts were captured, an "orchestration findings" section for anything that went wrong mechanically (permission denials, quoting issues, stale pending-review items), and an explicit "this is n=1 per condition, not a statistical comparison" caveat, matching this benchmark's own README.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/physics/results/2026-08-06-deepseek-v4-flash-shakedown.md
git commit -m "Add benchmark-physics DeepSeek V4 Flash shakedown results"
```

---

## Self-Review

**Spec coverage:** worktree/location (Task 1) — covered. `cases/`+`gold/` schema and both real cases (Tasks 3-4) — covered, including the `bonus_findings` extension called out in the spec. `control/` track with the GPQA→MMLU licensing substitution (Task 5) — covered. Harness `benchmark.py`/`protocol.json` copy-adapted with inherited known limitations (Tasks 2, 6) — covered. `README.md` isolation boundary (Task 7) — covered. Non-goals (no shared module, no scorer fixes, no runner shipped in-repo) — respected throughout, no task violates them. Shakedown run with OpenCode/DeepSeek-V4-Flash (Tasks 8-9) — covered, addressing the user's explicit request.

**Placeholder scan:** no TBD/TODO in any task. Task 8's permission-policy JSON is explicitly marked as a starting point to be confirmed against live `--help` output rather than asserted as certainly correct — that's an honest "verify against the tool at execution time" instruction, not a placeholder, since the concrete fallback content is fully specified.

**Type consistency:** concept-id strings introduced in Task 3/4's case and gold JSON are reused verbatim in Task 6's test fixtures (`negf-eta-broadening-artifact-near-zero-mode`, etc.) — checked. `benchmark.py` function signatures declared in each task's Interfaces block match the implementation in Task 6 Step 3. `bonus_findings` field appears consistently in `phys02`'s gold, case `answer_contract.hypothesis_fields`, and `score_answer`'s bonus-scoring logic.
