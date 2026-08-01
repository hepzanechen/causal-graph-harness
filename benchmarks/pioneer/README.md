# Causal-Graph Pioneer Benchmark

This is a six-case smoke benchmark for comparing the same bare agent with and
without the `causal-graph-research` skill. It validates the experimental
plumbing before investing in the proposed 30-case benchmark; it is too small
for a general performance claim.

The cases are deliberately small, frozen, synthetic incident replays modeled
on ordinary microservice failures. They require no network access or large
dataset download:

| Class | Count | Cases |
|---|---:|---|
| Straightforward single fault | 2 | `p01`, `p02` |
| Multi-hop root cause | 2 | `p03`, `p04` |
| Misleading observation | 1 | `p05` |
| Two simultaneous causes | 1 | `p06` |

## Isolation boundary

`cases/` is agent-visible. `gold/` is evaluator-only. A real run must copy the
selected public case into the agent sandbox and must not mount this repository,
the `gold/` directory, or the `score` command there. Merely telling an agent
not to read gold is not isolation.

The public broker requires a non-empty search query, preventing a one-call dump
of all evidence:

```bash
python -m benchmarks.pioneer.benchmark list
python -m benchmarks.pioneer.benchmark prompt p03
python -m benchmarks.pioneer.benchmark search p03 "latency retry"
python -m benchmarks.pioneer.benchmark read p03 ev-p03-04
```

The evaluator scores a structured answer after the sandbox has closed:

```bash
python -m benchmarks.pioneer.benchmark score p03 answer.json
```

Both conditions receive the prompt, evidence broker, and answer contract. The
treatment condition additionally receives the causal-graph skill and scripts.
Run each case once per condition for the pioneer (12 runs). Use fresh state,
the same pinned model/settings, no web, and the same evidence-query/time limit.
The exact v1 limits and fields to record are frozen in `protocol.json`.

The repository intentionally does not contain a model-provider runner: the
causal-graph package has no agent-runtime API, and silently choosing one here
would make the comparison provider-specific. A runner should translate its
provider's tool calls to the three public functions in `benchmark.py`, enforce
`protocol.json`, write the returned JSON answer, and invoke `score_answer` only
after the agent sandbox is destroyed.

## What this pioneer can establish

- Cases and evidence are accessible through a repeatable interface.
- Gold labels are structurally separable from agent-visible data.
- Both conditions produce machine-scoreable answers.
- The graph workflow completes and its overhead can be measured.
- At least the misleading and compound cases distinguish evidence-selection
  behavior from simple anomaly spotting.

It cannot establish statistical superiority. If both agents solve all six,
retain the two easy cases as overhead controls and replace `p03`–`p06` with
harder evidence packets before scaling to 30 cases.
