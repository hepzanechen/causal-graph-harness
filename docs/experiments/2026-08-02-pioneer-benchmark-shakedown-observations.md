# Experiment note: pioneer benchmark shakedown observations and improvements

Date: 2026-08-02  
Experiment run: 2026-08-01  
Model: `opencode/deepseek-v4-flash`  
Conditions: bare agent vs. agent instructed to follow the causal-graph
`AGENTS.md`

## Purpose and status

This note records what can and cannot be learned from the first six-case
pioneer benchmark run. The run successfully exercised both conditions on all
six cases, but it was a runner and scorer shakedown, not a valid accuracy
comparison. The cases were deliberately simple and the run exposed several
benchmark, orchestration, and harness issues that should be fixed before a
larger experiment.

The main conclusion is narrow: there is enough evidence to improve harness
reliability, efficiency, observability, and final-answer synthesis. There is
not yet enough evidence to change the Bayesian reasoning rules or claim that
the graph condition improves diagnosis.

## What was observed

At the semantic level, both conditions found every essential cause and the
correct propagation story in all six cases. Under a stricter manual rule that
required the complete material root set in one top-ranked hypothesis, a
complete chain, and a valid answer envelope, both conditions passed 4/6.

The deterministic scorer reported 0/6 joint success for both conditions. This
was a scorer failure: it compares normalized natural-language strings for
root causes and causal-edge endpoints. Correct paraphrases consequently
received zero credit. It also scores only the top hypothesis, so a compound
diagnosis can lose credit even when all causes and evidence appear elsewhere
in the answer.

The selected clean runs had the following aggregate costs:

| Condition | Input tokens | Output tokens | Agent steps | Model cost | Mean wall time |
|---|---:|---:|---:|---:|---:|
| Bare | 99,554 | 21,242 | 44 | $0.0374 | 34.1 s |
| Graph | 197,318 | 72,867 | 159 | $0.1490 | 112.6 s |
| Graph / bare | 1.98x | 3.43x | 3.61x | 3.99x | 3.30x |

This establishes material workflow overhead on easy cases. It does not show
that the overhead is unnecessary on difficult cases, because these evidence
packets were too easy to separate the conditions.

Individual cases exposed useful behavior:

- In `p03`, the bare agent promoted a transient cache rebalance to an
  additional root, while the graph agent retained the retry policy as the
  root. This is consistent with the intended benefit, but one case is not
  evidence of a general advantage.
- In `p05`, both agents found the certificate failure and propagation chain,
  but promoted an intermediate mechanism or deeper actor to an additional
  root. This exposed ambiguity between `root`, `trigger`, `contributor`, and
  `intermediate` causal roles.
- In `p06`, the graph agent found both material causes but placed them in two
  ranked hypotheses. A scorer that considers only the first hypothesis marked
  the compound diagnosis incomplete. The same run also encountered a stale
  pending-review item after a falsification/retry flow, revealing a real graph
  lifecycle defect.

All completed answers cited all critical evidence when citations were unioned
across the complete answer. However, the broker did not log which evidence was
returned or read, and the gold data did not distinguish supporting,
falsifying, and distracting evidence. The experiment therefore could not
measure the confirmation-bias resistance that the graph process is meant to
provide.

The first graph wave also exposed orchestration problems: OpenCode rejected
the absolute `AGENTS.md` read without a narrow external-directory policy, and
shell backticks in initial prompts were interpreted before reaching the
agent. Several agents returned fenced or wrapped JSON despite a JSON-only
instruction.

## Improvements justified by this run

### 1. Fix pending-review lifecycle correctness

Resolve the stale pending item left by a falsification check followed by a
retry. Add a regression test covering the complete queue, falsification,
retry, and resolution sequence. This is the highest-confidence harness change
because an actual execution reached the bad state.

### 2. Add explicit final diagnosis synthesis

Before emitting an answer, the armed agent should synthesize the whole active
graph rather than equating the first hypothesis with the diagnosis. The final
schema should contain a top-level `root_cause_set`, while ranked hypotheses
remain available for alternatives. Each reported cause should have an
explicit role:

- `root`: an independently material originating fault;
- `trigger`: an event that activated an existing failure condition;
- `contributor`: a condition that increased likelihood or impact;
- `intermediate`: a mechanism in the propagation chain.

This would make compound diagnoses stable across harmless differences in
answer organization and prevent intermediate mechanisms from being silently
treated as extra roots.

### 3. Make graph depth adaptive and define stopping rules

`AGENTS.md` already permits lightweight use, but the measured overhead shows
that agents need a more operational routing rule. A preflight should select
one of three depths:

1. evidence and facts only for simple, directly resolved questions;
2. deductions plus competing hypotheses for ambiguous questions;
3. causal edges, Bayesian updates, and falsification checks when causal
   attribution is consequential or credible alternatives remain.

The workflow should stop when the answer contract is satisfied, all material
alternatives have been checked, and further graph mutations are unlikely to
change the diagnosis. The change should reduce mechanical work without
weakening the audit trail.

### 4. Reduce CLI interaction cost without weakening determinism

The graph condition used 159 agent steps versus 44 for the bare condition.
Introduce a deterministic batch or transaction interface that can register a
set of evidence, facts, deductions, and proposed edges in one validated atomic
operation. The existing single-operation scripts should remain available for
inspection and recovery.

This is an ergonomic optimization, not permission to move validation or
Bayesian arithmetic into model-generated output.

### 5. Add evidence-trajectory observability

Persist an append-only trace of:

- searches and evidence IDs returned;
- evidence IDs opened or read;
- evidence cited in the final answer;
- evidence used in graph updates;
- evidence rejected, with the stated reason;
- explicit counterevidence searches and their result.

This is necessary to distinguish genuine falsification behavior from an agent
that cites all available evidence after already reaching a verdict.

### 6. Harden launcher and output boundaries

Package the minimal OpenCode permission policy needed to read the repository's
`AGENTS.md` while continuing to deny unrelated external directories. Construct
process arguments without shell-interpreted prompt text. Validate the final
JSON envelope before scoring, and allow a deterministic unwrapping repair for
format-only mistakes without altering diagnostic content.

## Benchmark and scoring changes required before evaluation

The scorer should follow established root-cause and evidence-evaluation
practice rather than exact free-text matching. The closest precedents are
[ITBench](https://openreview.net/pdf/d2122a3a706c4c7cd0d382ee9b13da641bd1fe5a.pdf),
which separates diagnosis, fault-propagation-chain quality, ranking, and time;
[RCAEval](https://arxiv.org/abs/2412.17015), which evaluates ranked root-cause
candidates; and [ALCE](https://arxiv.org/abs/2305.14627), which separates
citation correctness from citation completeness.

Use separate co-primary metrics rather than a single opaque weighted score:

- canonicalized root-cause set precision, recall, and F1;
- required causal-chain milestone or edge precision, recall, and F1.

Report strict joint success as a secondary metric: every material root found,
every required propagation milestone covered, and no major unsupported causal
claim. Score the complete diagnosis, not only the first hypothesis. Ranked
alternatives may additionally use Hit@1, Hit@3, and mean reciprocal rank.

Gold labels should include canonical concepts, accepted aliases, causal roles,
acceptable chain variants, critical supporting evidence, falsifying evidence,
and distractors. Unresolved semantic equivalence should be judged by reviewers
blind to the experimental condition. The rubric and gold labels must be frozen
before the next agent run.

Efficiency should remain a separate outcome: tokens, model cost, wall time,
agent steps, evidence reads, and cost per successful joint diagnosis. Do not
trade diagnostic correctness against cost through an arbitrary composite
weight.

## What this experiment does not justify

Do not use these results to:

- claim that the graph agent is more or less accurate than the bare agent;
- alter default priors, likelihood-ratio policy, posterior thresholds, or the
  high-confidence falsification gate;
- claim that falsification checks improve accuracy;
- optimize the workflow specifically around the single `p03` graph win;
- remove graph features because they were expensive on deliberately easy
  cases.

Those are hypotheses for a controlled rerun, not findings from this
shakedown.

## Next experimental gate

Before another comparison, fix the lifecycle defect, freeze the revised answer
contract and scorer, add evidence-trajectory logging, and remove launcher
confounds. Retain `p01` and `p02` as easy overhead controls, but replace or
harden at least three of `p03` through `p06` with cases containing plausible
distractors, competing causes, and evidence that can falsify an attractive
early explanation.

The six-case suite should then be rerun as a plumbing check. A performance
claim should wait for at least 30 cases with matched model settings and at
least three seeds per condition. Analysis should be paired by case, report
wins/losses/ties and confidence intervals, and avoid treating repeated seeds
as independent cases.

