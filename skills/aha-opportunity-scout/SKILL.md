---
name: aha-opportunity-scout
description: "After completing a technical, research, or repository task, surface one concrete, evidence-based next opportunity the user may not have considered, such as a beginner contribution path, a well-formed community question, a reusable artifact, or a small preventive improvement. Keep it optional and skip it when no useful adjacent move is supported by the task."
---

# Aha Opportunity Scout

Help the user see one useful step beyond the immediate request without turning the response into a brainstorm or silently expanding the assignment. Complete the requested work first. Then, only when the task provides enough evidence, offer the highest-value adjacent move.

## When to use this judgment

Look for an opportunity when the work involves investigating a repository, debugging a blocked problem, learning an unfamiliar system, making a decision, or producing an artifact that could be reused. Pay special attention when the user appears new to the project or asks for help finding an issue. Skip the extra suggestion when the user asks for a narrowly formatted output, is handling an urgent failure, or when every possible extension would be speculative or costly.

Use the conversation as the primary context. Treat the user's apparent experience, stated goals, previous choices, and constraints as soft context; do not claim to remember anything outside the available conversation. Inspect project evidence when available, such as `CONTRIBUTING` guidance, issue labels, discussion forums, release notes, test gaps, documentation gaps, or repeated manual steps. Do not invent a community channel, maintainer preference, issue status, or contribution opportunity.

## Find the opportunity

After solving or advancing the requested task:

1. Identify the user's underlying goal and the friction revealed by the work.
2. Generate a few candidate next moves across different angles: learning, community, contribution, documentation, automation, prevention, or reuse.
3. Prefer the candidate that is most directly supported by evidence, useful to this user, low-cost to try, reversible, and likely to create a concrete payoff.
4. Present one recommendation. Add a second only when it addresses a distinct need and is nearly as strong.

Good recommendations make the next action easy. They may include a specific file or page to inspect, a small first contribution, a targeted question for maintainers, a reproduction package, a test or documentation patch, or a reusable command/script. They should say why the opportunity appeared and what it unlocks.

For a beginner exploring an open-source issue, check whether the project exposes a contribution path such as `CONTRIBUTING`, `good first issue`, `help wanted`, discussions, or a supported chat/mailing list. If it does, suggest a small, respectful first move: read the project guidance, choose a bounded issue or docs/test improvement, or ask a focused question that includes the observed behavior, environment, what was tried, and the exact uncertainty. Never encourage mass-posting or contacting maintainers without a concrete question.

## Response shape

Keep the extra guidance concise and clearly optional. Use a compact block such as:

**One useful next move:** [specific action]

**Why it fits:** [evidence from this task and the user's apparent goal]

**First step:** [a low-risk action the user can take now, with a link, file, command, or draft question when available]

**Payoff:** [what this could unlock]

If the recommendation is a hypothesis rather than a verified route, say so and describe how to check it. Do not bury the requested answer under the suggestion, and do not perform external outreach, open issues, modify repositories, or create follow-up artifacts unless the user separately asks and authorizes that action.
