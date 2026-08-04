# Cross-Agent Plugin Manifests — Design

Date: 2026-08-05
Status: Approved (pending user spec review)
Related: `docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md`
(implements the "Future work: cross-agent distribution" item 1 from that spec)

## Problem

`AGENTS.md` already lets any agent that can read a repo and run shell
commands discover and drive the harness — that baseline is done. But it
requires the agent to read prose and decide to act on it. Claude Code
additionally auto-discovers `.claude/skills/causal-graph-research/SKILL.md`
as a first-class skill; Codex, Cursor, and (per investigation) OpenCode have
their own structured discovery mechanisms that would let them do the same,
instead of relying on an agent noticing and following `AGENTS.md` on its
own.

Separately, all ten scripts are invoked as `python scripts/<name>.py` —
repo-relative, so they only work if the agent's cwd is this exact checkout.
A plugin manifest that still points at repo-relative scripts only helps an
agent that happens to already be sitting in this repo; it does nothing for
the "install once, use in any repo" case the manifests exist to enable, and
the user's stated long-term intent is to publish this for real.

## Decision: build in the eventually-publishable shape now

Two ways to satisfy "agents auto-discover this harness":

- **Same-repo parity** — manifests pointing at scripts already in this
  checkout. Cheap, but the moment this gets published (the user's stated
  goal), every manifest and the skill doc gets rewritten anyway.
- **Standalone-installable shape** — cwd-independent commands, one
  canonical skill doc, manifests that work via a direct git-source
  reference today and need zero rework when a package name is registered
  later.

The expensive part of "standalone" isn't publishing — it's making the CLI
callable regardless of cwd. That's a one-time code change. This design
does that now and stops short of the actually-irreversible step (claiming
a PyPI name / registering a marketplace listing), which stays a deferred
follow-up.

**Explicitly out of scope for this design:** PyPI publication, a
`marketplace.json` listing, and a native OpenCode plugin (its project-local
skill discovery already reads `.claude/skills/*/SKILL.md`, confirmed by
testing against OpenCode's own docs — no new work needed there; a real
OpenCode plugin is a separate JS-language project this design doesn't
attempt).

## CLI restructuring

Today: 10 standalone scripts under `scripts/`, each with its own
`argparse` parser and a `main()` guarded by a `try/except ValidationError`
block in `if __name__ == "__main__"`.

After: one installed command, `causal-graph`, with one subcommand per
existing script, same flags, same behavior, same validation/exit-code
contract:

| Subcommand | Flags (unchanged from current scripts) |
|---|---|
| `add-evidence` | `--topic --adapter --content --source-ref` |
| `add-fact` | `--topic --statement --evidence-id (repeatable) --confidence {verified,reported,inferred} [--contradicts]` |
| `add-deduction` | `--topic --claim --supports [--logic-note]` |
| `propose-causal-edge` | `--topic --from --to --relation-type --prior` |
| `update-causal-edge` | `--topic --edge-id --evidence-id --likelihood-ratio [--correlated-with]` |
| `record-falsification-check` | `--topic --edge-id --alternative-hypothesis --counterevidence-search --result` |
| `revise-fact` | `--topic --fact-id --new-status --reason [--replacement-statement]` |
| `dispute-edge` | `--topic --edge-id --new-status --reason` |
| `review-queue` | `--topic` |
| `resolve-pending` | `--topic --id --action {approve,reject,amend} [--amended-likelihood-ratio]` |

Structure:
- Each script's body moves verbatim (module-level logic unchanged) into
  `causal_graph/commands/<name>.py`, exposing a `main(argv=None)` that
  returns an exit code instead of calling `sys.exit` directly, so it's
  callable both as a subcommand and from tests without subprocess.
- `causal_graph/cli.py` (already exists, currently just
  `current_agent_id()`) gains the top-level `main()`: builds an
  `argparse.ArgumentParser` with subparsers, dispatches to the matching
  command module, translates `ValidationError` into the existing
  `error: ...` stderr message + exit code 1.
- `pyproject.toml` adds:
  ```toml
  [project.scripts]
  causal-graph = "causal_graph.cli:main"
  ```
  and `[tool.setuptools] packages` gains `"causal_graph.commands"`.
- `scripts/*.py` at repo root are deleted. The project's own status is
  "prototype, interfaces may change" (README) — carrying two parallel
  invocation styles (bare script vs. installed command) forward
  indefinitely is exactly the redundant-maintenance cost this design
  exists to avoid. `research/agent-install-surface/` (recorded data, not
  scripts) is untouched.
- Storage semantics are unchanged: `causal-graph <subcommand> --topic T`
  still resolves `research/T/graph/` relative to the caller's cwd, same as
  today — installing the command doesn't change where data lives, same as
  `git` operating on whatever repo you're standing in.

## Canonical skill doc

New `skills/causal-graph-research/SKILL.md` at repo root (mirrors where
the `obra/superpowers` repo — the model this design and its parent spec
both cite — keeps its shared skill content). Same frontmatter/content
shape as the current `.claude/skills/causal-graph-research/SKILL.md`, with
its body's script-invocation examples updated to `causal-graph
<subcommand>`.

`.claude/skills/causal-graph-research/SKILL.md` becomes a symlink to
`../../../skills/causal-graph-research/SKILL.md` (three levels up from
`.claude/skills/causal-graph-research/` to repo root, then back down into
the shared dir) — one file to keep in sync,
not two copies that can drift. (Git tracks symlinks natively on
Linux/macOS; a checkout on a filesystem without symlink support would see
a text file containing the relative path instead of the rendered content —
a minor, documented degradation, consistent with the sandbox quirks
`AGENTS.md` already calls out elsewhere.)

## Manifests

Three new files, each declaring `"skills": "./skills/"` against the shared
directory above, and consistent identity fields (`name:
causal-graph-harness`, `version` matching `pyproject.toml`'s `0.1.0`,
`repository: https://github.com/hepzanechen/causal-graph-harness`):

- `.claude-plugin/plugin.json` — installable as a Claude Code plugin from
  a git source (no marketplace listing required for a direct-source
  install).
- `.codex-plugin/plugin.json`
- `.cursor-plugin/plugin.json`

No `.opencode/` manifest (see Decision above).

## Documentation updates

- `AGENTS.md`: replace every `python scripts/<name>.py` example with
  `causal-graph <subcommand>`; update the "Install" section to note
  `causal-graph` is now on `PATH` after `pip install -e .`; update the CLI
  reference table's script names to subcommand names.
- `README.md`: update the quick-start snippet the same way.
- Parent spec (`2026-08-01-causal-graph-agent-harness-design.md`): amend
  the "Future work: cross-agent distribution" section's item 1 with a
  one-line pointer to this spec as the concrete design, leaving the
  historical deferral text intact.

## Testing

- Existing script tests (`tests/test_propose_causal_edge.py`,
  `tests/test_update_causal_edge.py`, plus any others under `tests/`)
  switch from copying `.py` files into a tmp dir and subprocess-invoking
  them, to either (a) subprocess-invoking the installed `causal-graph`
  console script, or (b) importing `causal_graph.commands.<name>.main()`
  directly and asserting on its return code / captured stdout-stderr.
  Preferred: (b) where the test doesn't specifically need process
  isolation — it's faster and matches how the rest of the suite already
  imports `causal_graph.storage` directly. Assertions and fixtures
  otherwise unchanged.
- New: one test per manifest file asserting it parses as valid JSON,
  contains `name`/`version`/`skills`, and that the `skills` path resolves
  to a directory containing `causal-graph-research/SKILL.md`.
- New: a test invoking `causal-graph --help` and `causal-graph
  add-fact --help` (via the installed entry point) to catch
  subparser-wiring regressions the unit tests wouldn't.

## Non-goals

- PyPI publication, package-name registration.
- A `marketplace.json` listing for any agent.
- A native OpenCode plugin (JS-based; separate project).
- `gemini-extension.json` — not covered by this pass; left for a later
  design/implementation once there's a concrete reason to prioritize it.
- Any change to the graph data model, Bayesian arithmetic, or process
  skill steps defined in the parent spec — this is purely a distribution/
  invocation-surface change.
