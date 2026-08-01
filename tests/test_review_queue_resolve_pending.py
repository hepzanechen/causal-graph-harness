import json
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "add_deduction.py", "propose_causal_edge.py",
           "update_causal_edge.py", "review_queue.py", "resolve_pending.py", "revise_fact.py",
           "record_falsification_check.py", "dispute_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_pending_edge_update(tmp_path):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.5",
    ], cwd=tmp_path).stdout.strip()
    _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    return edge, ev


def test_review_queue_lists_pending_with_tier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    _seed_pending_edge_update(tmp_path)
    result = _run("review_queue.py", ["--topic", "t"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout)
    assert len(items) == 1
    assert items[0]["tier"] in ("urgent", "normal")


def test_resolve_pending_approve_applies_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    pending = storage.load_json_list("t", "pending_review")
    item_id = pending[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "approve",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert storage.load_json_list("t", "pending_review") == []
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert len(edges[edge]["updates"]) == 1


def test_resolve_pending_reject_discards_without_applying(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "reject"], cwd=tmp_path)
    assert storage.load_json_list("t", "pending_review") == []
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"] == []


def test_resolve_pending_amend_uses_replacement_ratio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "amend",
        "--amended-likelihood-ratio", "3.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"][0]["likelihood_ratio"] == 3.0


def test_resolve_pending_approve_fact_revision_cascades_stale_to_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    d1 = _run("add_deduction.py", ["--topic", "t", "--claim", "C", "--supports", f"fact:{f1}"], cwd=tmp_path).stdout.strip()
    e1 = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"deduction:{d1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path).stdout.strip()

    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "agent-1")
    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "was wrong",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout

    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    item_id = pending[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "approve",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = {f["id"]: f for f in storage.load_json_list("t", "facts")}
    deds = {d["id"]: d for d in storage.load_json_list("t", "deductions")}
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert facts[f1]["status"] == "retracted"
    assert deds[d1]["status"] == "stale"
    assert edges[e1]["status"] == "stale"


def test_resolve_pending_approve_stale_causal_edge_update_after_retry_errors(tmp_path, monkeypatch):
    # If the documented falsification-retry pattern (record check, then
    # retry the same update) is used, the original diverted pending item
    # becomes stale once the retry applies directly. Approving that stale
    # item afterwards must not silently double-apply the same evidence.
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    _run("record_falsification_check.py", [
        "--topic", "t", "--edge-id", edge,
        "--alternative-hypothesis", "alt", "--counterevidence-search", "search", "--result", "null result",
    ], cwd=tmp_path)
    retry = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert retry.returncode == 0, retry.stderr
    assert "queued for review" not in retry.stdout

    result = _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "approve"], cwd=tmp_path)
    assert result.returncode != 0
    assert "already been applied" in result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert len(edges[edge]["updates"]) == 1


def test_resolve_pending_approve_causal_edge_update_rejects_retracted_edge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    _run("dispute_edge.py", ["--topic", "t", "--edge-id", edge, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)

    result = _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "approve"], cwd=tmp_path)
    assert result.returncode != 0
    assert "retracted" in result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"] == []


def test_resolve_pending_approve_contradiction_supersedes_old_fact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    first = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    d1 = _run("add_deduction.py", ["--topic", "t", "--claim", "C", "--supports", f"fact:{first}"], cwd=tmp_path).stdout.strip()
    _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", first,
    ], cwd=tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "approve"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = storage.load_json_list("t", "facts")
    assert len(facts) == 2
    old_fact = next(f for f in facts if f["id"] == first)
    new_fact = next(f for f in facts if f["id"] != first)
    assert old_fact["status"] == "superseded"
    assert new_fact["status"] == "active"
    assert new_fact["supersedes_id"] == first
    deds = {d["id"]: d for d in storage.load_json_list("t", "deductions")}
    assert deds[d1]["status"] == "stale"
    assert storage.load_json_list("t", "pending_review") == []


def test_resolve_pending_reject_contradiction_discards_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    first = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", first,
    ], cwd=tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "reject"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = storage.load_json_list("t", "facts")
    assert len(facts) == 1
    assert facts[0]["id"] == first
    assert facts[0]["status"] == "active"
    assert storage.load_json_list("t", "pending_review") == []


def test_resolve_pending_approve_contradiction_rejects_already_superseded_fact(tmp_path, monkeypatch):
    # Two --contradicts calls against the same target fact, both queued, then
    # both approved in sequence: the second approval must not silently
    # re-supersede an already-superseded fact.
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    first = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    _run("add_fact.py", ["--topic", "t", "--statement", "not A (v1)", "--evidence-id", ev, "--confidence", "reported", "--contradicts", first], cwd=tmp_path)
    _run("add_fact.py", ["--topic", "t", "--statement", "not A (v2)", "--evidence-id", ev, "--confidence", "reported", "--contradicts", first], cwd=tmp_path)
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 2

    first_result = _run("resolve_pending.py", ["--topic", "t", "--id", pending[0]["id"], "--action", "approve"], cwd=tmp_path)
    assert first_result.returncode == 0, first_result.stderr

    second_result = _run("resolve_pending.py", ["--topic", "t", "--id", pending[1]["id"], "--action", "approve"], cwd=tmp_path)
    assert second_result.returncode != 0
    assert "not active" in second_result.stderr

    facts = storage.load_json_list("t", "facts")
    assert len(facts) == 2  # original (now superseded) + exactly one winner


def test_resolve_pending_approve_fact_revision_creates_replacement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "agent-1")
    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "superseded", "--reason", "corrected",
        "--replacement-statement", "A, corrected",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout

    item_id = storage.load_json_list("t", "pending_review")[0]["id"]
    result = _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "approve"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = storage.load_json_list("t", "facts")
    assert len(facts) == 2
    old_fact = next(f for f in facts if f["id"] == f1)
    new_fact = next(f for f in facts if f["id"] != f1)
    assert old_fact["status"] == "superseded"
    assert new_fact["statement"] == "A, corrected"
    assert new_fact["status"] == "active"
    assert new_fact["supersedes_id"] == f1


def test_resolve_pending_amend_rejected_for_fact_revision(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "agent-1")
    _run("revise_fact.py", ["--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "amend", "--amended-likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "not supported" in result.stderr


def test_resolve_pending_amend_rejects_invalid_likelihood_ratio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "amend", "--amended-likelihood-ratio", "-3.0",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "must be > 0" in result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"] == []
