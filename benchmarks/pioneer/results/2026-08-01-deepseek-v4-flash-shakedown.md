# DeepSeek V4 Flash Pioneer Shakedown

Date: 2026-08-01  
Model: `opencode/deepseek-v4-flash`  
Conditions: bare agent vs. agent instructed to follow `/home/kt/zero/AGENTS.md`

## Verdict

This run successfully exercised all six cases in both conditions, but it is a
runner/scorer shakedown, not a valid statistical comparison. Both conditions
identified the essential cause or causes in all six cases. Under a stricter
root-set/output-contract review, each condition passed 4/6. The cases are too
easy to expose a clear skill advantage, while the graph workflow adds material
overhead.

The deterministic scorer is not currently usable for natural agent answers:
it requires exact normalized strings for root faults and causal-edge endpoints.
All semantically correct paraphrases therefore received zero causal-chain
recall and failed exact root matching. Automatic result: 0/6 joint success for
both conditions.

## Selected clean-run measurements

| Condition | Input tokens | Output tokens | Agent steps | Model cost | Mean wall time |
|---|---:|---:|---:|---:|---:|
| Bare | 99,554 | 21,242 | 44 | $0.0374 | 34.1 s |
| Graph | 197,318 | 72,867 | 159 | $0.1490 | 112.6 s |
| Graph / bare | 1.98x | 3.43x | 3.61x | 3.99x | 3.30x |

Retry and interrupted-session costs are excluded, so actual operational cost
was higher than this table.

## Manual strict review

The strict review requires the exact material root-cause set in one top-ranked
hypothesis, a materially complete chain, and a valid answer envelope.

| Case | Bare | Graph | Observation |
|---|---|---|---|
| `p01` | Pass | Pass | Both found the unbounded receipt cache, OOM, and 503 chain. |
| `p02` | Pass | Pass | Both found the expired catalog database credential. |
| `p03` | Fail | Pass | Bare promoted the transient cache rebalance to a second root; graph kept the retry policy as root. |
| `p04` | Pass | Pass | Both found the media-service DNS resolver misconfiguration. |
| `p05` | Fail | Fail | Both found the certificate failure and correct chain but promoted an additional mechanism/actor to a root. Bare also returned an invalid nested answer envelope. |
| `p06` | Pass | Fail | Both found the payment endpoint and missing index; graph split them into two ranked hypotheses instead of one compound top hypothesis. |
| **Total** | **4/6** | **4/6** | No measured quality advantage. |

At the looser semantic level—did the answer contain every essential cause and
the correct propagation story?—both conditions were 6/6. This ceiling confirms
that the pioneer evidence packets are primarily plumbing tests.

## Evidence behavior

- Every completed answer cited all critical evidence when citations were
  unioned across the whole answer.
- The current scorer considers only the top hypothesis, reducing graph `p06`
  critical-evidence recall to 0.6667 even though its second hypothesis cited the
  remaining payment evidence.
- Gold files do not separately label falsifying evidence or distractors, and
  the broker does not persist which evidence IDs were returned/read. The run
  therefore cannot quantify the evidence-selection behavior the graph skill is
  intended to improve.

## Orchestration findings

1. The first parallel graph wave stopped after initial filesystem tool calls.
   OpenCode auto-rejected `external_directory` permission after agents read the
   requested absolute `AGENTS.md` path.
2. A per-run `opencode.json` allowing only `/home/kt/zero/AGENTS.md` and denying
   other external directories resolved that failure for clean retries.
3. Initial shell quoting used backticks in prompts, which Bash interpreted
   before OpenCode received them. The selected graph retries and bare `p05`
   retry used safe single-quoted prompts; the other bare runs still discovered
   the broker despite losing the inline example commands. This is a comparison
   confound and another reason not to treat the run as a final A/B result.
4. Graph `p06` hit a stale pending-review item after a falsification/retry flow,
   exposing a real harness lifecycle issue. The agent still completed its
   diagnosis.
5. Several agents added prose or Markdown fences despite the JSON-only
   instruction. One bare answer nested the payload under `answer_contract`.

## Required changes before a scored rerun

1. Replace exact-string causal scoring with canonical concept IDs, accepted
   aliases, or blinded semantic adjudication.
2. Decide whether a compound diagnosis must put all causes in one hypothesis;
   encode and enforce that contract explicitly.
3. Add `falsifying_evidence_ids` and `distractor_evidence_ids` to gold, and log
   every evidence ID returned and read.
4. Package the narrow OpenCode permission policy with each sandbox and generate
   process arguments without shell-interpreted prompt text.
5. Keep `p01`/`p02` as easy overhead controls, but replace or harden at least
   three of `p03`–`p06` before expecting a behavioral separation.
6. Fix the pending-review stale-item lifecycle before using graph compliance as
   a treatment-quality signal.

## OpenCode session IDs

These sessions remain in OpenCode's local session store for later export.

| Case | Bare | Graph |
|---|---|---|
| `p01` | `ses_043105d3cffeZkpB4FHbjhkiaS` | `ses_0429bd85cffex5DGmbc3KE9W6P` |
| `p02` | `ses_043105c62ffeq0QlzSmG9UVTkw` | `ses_043085a55ffeZ1x0D2HayLa9f1` |
| `p03` | `ses_0431073cfffeHGXN420lj7n2n1` | `ses_043084aabffexfgBzS1AC4t2J7` |
| `p04` | `ses_04310a7d1ffeXtHsYJAjTZmsKE` | `ses_043084bb6ffe08l66cmGtzWW4O` |
| `p05` | `ses_03eecb4feffe4VXI5XbZ9h4ckB` | `ses_0428d12d4ffeX6PEPuXOCihZgD` |
| `p06` | `ses_043109922ffedEdrycRJbAjZVq` | `ses_0428ab944ffeNlZIWTJZ2Quqhg` |
