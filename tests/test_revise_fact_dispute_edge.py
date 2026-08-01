import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "add_deduction.py",
           "propose_causal_edge.py", "revise_fact.py", "dispute_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_retracting_root_fact_cascades_stale_to_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    d1 = _run("add_deduction.py", ["--topic", "t", "--claim", "C", "--supports", f"fact:{f1}"], cwd=tmp_path).stdout.strip()
    e1 = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"deduction:{d1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path).stdout.strip()

    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "was wrong",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = {f["id"]: f for f in storage.load_json_list("t", "facts")}
    deds = {d["id"]: d for d in storage.load_json_list("t", "deductions")}
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert facts[f1]["status"] == "retracted"
    assert deds[d1]["status"] != "active"
    assert edges[e1]["status"] != "active"


def test_agent_revising_verified_fact_is_queued_not_applied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "agent-1")
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "contested", "--reason", "agent thinks it's wrong",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout
    facts = {f["id"]: f for f in storage.load_json_list("t", "facts")}
    assert facts[f1]["status"] == "active"
    pending = storage.load_json_list("t", "pending_review")
    assert pending[0]["kind"] == "fact_revision"


def test_dispute_edge_updates_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    e1 = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path).stdout.strip()

    result = _run("dispute_edge.py", [
        "--topic", "t", "--edge-id", e1, "--new-status", "contested", "--reason", "questionable",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[e1]["status"] == "contested"
