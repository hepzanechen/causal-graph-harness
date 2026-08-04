from causal_graph import storage
from tests.cli_support import run_cli as _run


def test_retracting_root_fact_cascades_stale_to_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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


def test_revise_fact_replacement_statement_requires_superseded_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()

    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "wrong",
        "--replacement-statement", "A, corrected",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "requires --new-status superseded" in result.stderr


def test_dispute_edge_updates_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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
