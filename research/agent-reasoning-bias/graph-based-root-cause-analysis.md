# Graph-based approaches to LLM agent verdict-then-cherry-pick bias

Date: 2026-08-01

## Problem statement

When an LLM agent is given a diagnostic/research problem, it tends to explore
the context, form a verdict early, then search for evidence that supports
that verdict — rather than:

1. Considering deeper root causes beyond the first plausible one, or
2. Considering whether multiple factors are jointly responsible.

## Proposed idea

Use graph theory to structure the reasoning instead of letting it run as an
unstructured chain:

- **Fact graph** — nodes are verified/true facts, established first, before
  any interpretation happens.
- **Deduction graph** — nodes are candidate inferences/claims, edges are
  logical dependencies on the fact graph and on each other.
- **Probabilistic causal graph** — edges carry likelihoods, updated via
  Bayesian updating as new evidence arrives, so multiple competing (or
  co-occurring) causes can be tracked simultaneously instead of collapsing to
  one verdict.

## Related work found

The three layers each map to an existing research thread — this is a
combination of known techniques, not unclaimed territory.

| Layer | Maps to | Key reference |
|---|---|---|
| Fact graph | Knowledge-graph-grounded reasoning: link each reasoning step to KG nodes so claims stay traceable | [Grounding LLM Reasoning with Knowledge Graphs](https://arxiv.org/abs/2502.13247) |
| Deduction graph | Graph-of-Thought / "Reasoning Graph Verifier": structure multiple candidate reasoning chains into a graph, check cross-chain consistency instead of trusting one linear chain | referenced in KG-grounding survey above |
| Causal graph + Bayesian edge updates | RCA/AIOps research already doing this: LLM-guided causal graph construction/evolution, validated against telemetry | [EvoCause: LLM-Guided Evolution of Causal Graphs for Root Cause Analysis](https://arxiv.org/html/2607.27290), [Causal-LLM (hybrid causal discovery + LLM)](https://www.preprints.org/manuscript/202602.1711), [Fault inference diagnosis via causal network + LLM-enhanced KG](https://www.sciencedirect.com/science/article/pii/S100093452500166X), [Causely: how causal reasoning addresses LLM limitations in observability](https://www.causely.ai/blog/how-causal-reasoning-addresses-the-limitations-of-llms-in-observability) |

## The key finding: the bias is in evidence *selection*, not weighing

The most load-bearing result for this idea: **"Failing to Falsify: Evaluating
and Mitigating Confirmation Bias in Language Models"**
([arxiv 2604.02485](https://arxiv.org/pdf/2604.02485)) shows that confirmation
bias in LLM agents shows up in *which evidence the model chooses to look
for*, not in how it interprets evidence once found. This means:

> A graph structure alone (fact graph → deduction graph → causal graph) fixes
> how evidence is *aggregated and weighed*, but does **not** by itself fix
> the upstream problem of biased evidence *search*. The graph will faithfully
> encode a one-sided investigation if the agent only ever looked for
> confirming evidence to begin with.

Independently, the Waterloo ISE Lab's study of LLM RCA failures
([project page](https://uwaterloo.ca/waterloo-intelligent-systems-engineering-lab/projects/llm-reasoning-failures-cloud-root-cause-analysis))
names the same dominant failure modes: anchoring bias, stalled progress,
arbitrary evidence selection, and failure to update beliefs — and notes that
adding more agentic complexity (more steps, more tool calls) often
*compounds* these errors rather than resolving them. Scaffolding is not a
free fix.

## Countermeasure converged on by the field: an explicit falsification/contrarian role

Multiple independent lines of work land on the same fix: give a dedicated
agent role the *structural* job of attacking the current leading hypothesis,
rather than relying on the graph/aggregation layer to surface disagreement
after the fact.

- **AutoResearchClaw** ([arxiv 2605.20025](https://arxiv.org/pdf/2605.20025)):
  structured debate with complementary epistemic roles — Innovator (proposes
  high-risk hypotheses), Pragmatist (feasibility), **Contrarian** (actively
  seeks weaknesses/confounds) — synthesized by a separate judge.
- **Argumentative Experience** ([arxiv 2412.04629](https://arxiv.org/html/2412.04629v3)):
  multi-persona debate specifically to reduce confirmation bias on
  controversial/ambiguous issues.
- General multi-agent debate literature: effective when agents are diverse
  (different models/seeds/role prompts), critiques are grounded in explicit
  facts/steps, and a judge rewards verifiable reasoning over confident
  assertion — but note *identity bias* (sycophancy between agents) is a
  documented failure mode of naive multi-agent debate setups
  ("Measuring and Mitigating Identity Bias in Multi-Agent Debate via
  Anonymization", [arxiv 2510.07517](https://arxiv.org/html/2510.07517v1)).

## Recommendation

Build the fact-graph → deduction-graph → causal-graph (Bayesian edge update)
stack as planned, but add a falsification/contrarian step **at hypothesis
generation time, before the causal graph is built** — not just as a
post-hoc check on the finished graph. The graph formalism solves
aggregation/multi-factor tracking; it does not solve biased search. Also
anonymize/diversify agent roles in any debate step to avoid sycophancy
between sub-agents.

## Other references surfaced but not yet read in depth

- [Cloud Atlas — causal graphs synthesized from docs/telemetry/deployment feedback](https://www.causely.ai/blog/how-causal-reasoning-addresses-the-limitations-of-llms-in-observability)
- [TAMO: Fine-Grained Root Cause Analysis via Tool-Assisted LLM Agent](https://arxiv.org/html/2504.20462v1)
- [Large Language Models for Agentic NetOps and AIOps: Architectures, Evaluation, and Safety](https://arxiv.org/pdf/2605.12729)
- [Can LLM Agents Really Debate? A Controlled Study of Multi-Agent Debate in Logical Reasoning](https://arxiv.org/pdf/2511.07784)
- [From Debate to Deliberation: Structured Collective Reasoning with Typed Epistemic Acts](https://arxiv.org/pdf/2603.11781)
- [awesome-LLM-AIOps (curated paper/tool list)](https://github.com/Jun-jie-Huang/awesome-LLM-AIOps)
