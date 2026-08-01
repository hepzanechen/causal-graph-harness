# tests/test_update_causal_edge.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py", "update_causal_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_edge(tmp_path, prior="0.3"):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", prior,
    ], cwd=tmp_path).stdout.strip()
    return edge, ev


def test_update_causal_edge_applies_moderate_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["posterior"] > edges[0]["prior"]
    assert len(edges[0]["updates"]) == 1
    assert storage.load_json_list("t", "pending_review") == []


def test_update_causal_edge_diverts_when_crossing_high_confidence_without_falsification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.5")
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["updates"] == []  # not applied
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    assert pending[0]["kind"] == "causal_edge_update"
