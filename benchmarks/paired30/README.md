# Paired-30 causal investigation benchmark

This is the preregistered successor to the six-case pioneer shakedown. It
contains 30 frozen synthetic incident packets, each with an attractive
alternative, explicit counterevidence, a causal propagation chain, a recovery
observation, and unrelated noise. The cases model distinct operational failure
mechanisms rather than surface variants of one template.

## Fairness changes from pioneer v1

- Agents identify opaque evidence-event IDs, eliminating exact free-text
  matching.
- Root causes are a whole-answer set, independent of ranked hypothesis layout.
- Compound incidents may contain multiple causal paths.
- Accuracy, evidence behavior, calibration, and efficiency remain separate
  outcomes; there is no arbitrary composite score.
- Searches and reads are written to an append-only `evidence_trace.jsonl`.
- Gold labels separately identify critical support, falsifying evidence, and
  distractors.
- Runs are paired by case and repetition, randomized deterministically, and
  interleaved across conditions.

## Frozen protocol

Use `protocol.json`. The first repetition is an integrity wave: score and audit
all 60 runs before authorizing repetitions two and three. This protects the
budget from another runner/scorer failure. The final planned study contains
180 runs: 30 cases x 2 conditions x 3 repetitions.

Every run starts in a fresh directory. The run directory receives only the
selected public case, the public broker, and—in the treatment condition—the
causal-graph scripts and instructions. It never receives `gold.json`,
`build_dataset.py`, another case, or another run directory.

Primary outcomes are root-cause set F1 and causal-chain F1. Joint success is a
secondary strict outcome. Supporting-evidence F1, falsifying-evidence recall,
distractor rejection/adoption, Brier score, tokens, cost, model steps, and wall
time are reported separately.

The 30 cases are the statistical units. Repetitions measure within-case model
variation and must not be counted as 90 independent cases. Compare conditions
with paired case-level deltas and a hierarchical bootstrap that samples cases,
then repetitions within cases. Use paired strict-success analysis only as a
secondary sensitivity check.

## Broker commands inside a run sandbox

```bash
python3 benchmark.py prompt c01
python3 benchmark.py search c01 "memory cache"
python3 benchmark.py read c01 ev-c01-05
```

Scoring is evaluator-only:

```bash
python3 -m benchmarks.paired30.benchmark score c01 answer.json
```

