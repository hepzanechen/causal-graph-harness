import json
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py",
           "update_causal_edge.py", "review_queue.py", "resolve_pending.py")


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
