import subprocess
import sys

from causal_graph.cli import _COMMANDS


def test_top_level_help_lists_all_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    for name in _COMMANDS:
        assert name in result.stdout


def test_subcommand_help_shows_its_flags():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "add-fact", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--statement" in result.stdout
    assert "--confidence" in result.stdout


def test_unknown_subcommand_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "causal_graph.cli", "not-a-command"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
