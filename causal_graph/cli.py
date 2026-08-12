import argparse
import sys

from .agent import current_agent_id  # noqa: F401 (re-exported for tests/test_sanity.py)
from .commands import (
    add_evidence, add_fact, add_deduction, propose_causal_edge,
    update_causal_edge, record_falsification_check, revise_fact, dispute_edge,
    review_queue, resolve_pending,
)
from .schema import ValidationError

_COMMANDS = {
    "add-evidence": add_evidence,
    "add-fact": add_fact,
    "add-deduction": add_deduction,
    "propose-causal-edge": propose_causal_edge,
    "update-causal-edge": update_causal_edge,
    "record-falsification-check": record_falsification_check,
    "revise-fact": revise_fact,
    "dispute-edge": dispute_edge,
    "review-queue": review_queue,
    "resolve-pending": resolve_pending,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="causal-graph")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module in _COMMANDS.items():
        sub = subparsers.add_parser(name)
        module.add_arguments(sub)
    args = parser.parse_args(argv)
    module = _COMMANDS[args.command]
    try:
        module.run(args)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
