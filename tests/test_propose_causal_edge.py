import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py",
                 "propose_causal_edge.py", "revise_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_fact(tmp_path, statement):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    return _run("add_fact.py", ["--topic", "t", "--statement", statement, "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()


def test_propose_causal_edge_rejects_unknown_node(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    f1 = _seed_fact(tmp_path, "A")
    result = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", "fact:missing",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown node reference" in result.stderr


def test_propose_causal_edge_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    f1 = _seed_fact(tmp_path, "memory limit cut")
    f2 = _seed_fact(tmp_path, "job OOM-killed")

    result = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edge_id = result.stdout.strip()
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["id"] == edge_id
    assert edges[0]["prior"] == 0.3
    assert edges[0]["posterior"] == 0.3
    assert edges[0]["updates"] == []
    assert edges[0]["falsification_checks"] == []


def test_propose_causal_edge_rejects_inactive_node(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    f1 = _seed_fact(tmp_path, "A")
    f2 = _seed_fact(tmp_path, "B")
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "human")
    _run("revise_fact.py", ["--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)

    result = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "not active" in result.stderr
