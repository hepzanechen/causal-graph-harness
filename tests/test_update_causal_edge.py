# tests/test_update_causal_edge.py
from causal_graph import storage
from tests.cli_support import run_cli as _run


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


def test_update_causal_edge_diverts_on_reversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.3")

    # Establish an upward trend: prior 0.3 -> posterior ~0.865, well short of the
    # 0.9 high-confidence threshold, so this first update applies directly.
    first = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "15.0",
    ], cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert "queued for review" not in first.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["updates"]) == 1
    posterior_after_first = edges[0]["posterior"]
    assert posterior_after_first < 0.9

    # Second update: a distinct piece of evidence with a sharply opposing
    # likelihood ratio that drags the trial posterior back down far enough
    # (>= 2x odds shift against the uptrend) to trigger is_reversal, without
    # also crossing the high-confidence threshold.
    ev2 = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c2", "--source-ref", "r2"], cwd=tmp_path).stdout.strip()
    second = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev2, "--likelihood-ratio", "0.01",
    ], cwd=tmp_path)
    assert second.returncode == 0, second.stderr
    assert "queued for review" in second.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["updates"]) == 1  # reversal update was NOT applied
    assert edges[0]["posterior"] == posterior_after_first  # unchanged
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    assert pending[0]["kind"] == "causal_edge_update"


def test_update_causal_edge_applies_when_falsification_check_already_recorded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.5")

    # Seed a falsification check directly on the edge record (Task 12's
    # record_falsification_check.py doesn't exist yet at this point in the plan).
    edges = storage.load_json_list("t", "causal_edges")
    edges[0]["falsification_checks"] = [{"note": "checked for confounders", "result": "no falsification found"}]
    storage.upsert("t", "causal_edges", edges[0])

    # Same trigger condition as the "diverts without falsification" test
    # (prior 0.5, LR 50.0 crosses 0.9) but this time the gate should open
    # because a falsification check is already on record.
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" not in result.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["updates"]) == 1
    assert edges[0]["posterior"] > edges[0]["prior"]
    assert storage.load_json_list("t", "pending_review") == []


def test_update_causal_edge_rejects_duplicate_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    first = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert first.returncode == 0, first.stderr

    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "3.0",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "already been applied" in result.stderr


def test_update_causal_edge_rejects_unknown_correlated_with(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "2.0",
        "--correlated-with", "ev_never_applied",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "not yet applied to this edge" in result.stderr


def test_update_causal_edge_rejects_retracted_edge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    _run("dispute_edge.py", ["--topic", "t", "--edge-id", edge, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)

    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "retracted" in result.stderr


def test_update_causal_edge_reaffirms_stale_edge_on_successful_apply(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    ev2 = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c2", "--source-ref", "r2"], cwd=tmp_path).stdout.strip()

    # Make the edge stale by retracting its from_node fact (verified facts
    # need a human agent id to apply the retraction directly).
    edges = storage.load_json_list("t", "causal_edges")
    from_fact_id = edges[0]["from_node"].split(":", 1)[1]
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "human")
    _run("revise_fact.py", ["--topic", "t", "--fact-id", from_fact_id, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["status"] == "stale"

    # Re-running the normal update path is the documented reaffirmation
    # mechanism: it should apply and bring the edge back to active.
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev2, "--likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["status"] == "active"
