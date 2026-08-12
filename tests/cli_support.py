import subprocess
import sys

_SUBCOMMAND = {
    "add_evidence.py": "add-evidence",
    "add_fact.py": "add-fact",
    "add_deduction.py": "add-deduction",
    "propose_causal_edge.py": "propose-causal-edge",
    "update_causal_edge.py": "update-causal-edge",
    "record_falsification_check.py": "record-falsification-check",
    "revise_fact.py": "revise-fact",
    "dispute_edge.py": "dispute-edge",
    "review_queue.py": "review-queue",
    "resolve_pending.py": "resolve-pending",
}


def run_cli(script, args, cwd):
    """Invoke the causal-graph CLI's subcommand for `script` (its old
    scripts/<script> filename, kept as the lookup key so every test file's
    existing `_run("add_fact.py", [...], cwd=...)` call sites don't need to
    change — only each file's local `_run` definition does).
    """
    return subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", _SUBCOMMAND[script], *args],
        cwd=cwd, capture_output=True, text=True,
    )
