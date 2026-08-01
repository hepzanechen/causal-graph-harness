import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_add_fact_requires_known_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "x", "--evidence-id", "missing",
        "--confidence", "verified",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown evidence id" in result.stderr


def test_add_fact_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "OOM killed the job", "--evidence-id", ev,
        "--confidence", "verified",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    fact_id = result.stdout.strip()
    facts = storage.load_json_list("t", "facts")
    assert facts[0]["id"] == fact_id
    assert facts[0]["status"] == "active"
    assert facts[0]["evidence_ids"] == [ev]


def test_add_fact_with_contradicts_queues_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()
    first = _run("add_fact.py", [
        "--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", first,
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    assert pending[0]["kind"] == "contradiction"
    assert pending[0]["contradicts_fact_id"] == first
    assert pending[0]["candidate_fact"]["statement"] == "not A"

    # The contradicting fact is diverted, not applied -- the graph must not
    # simultaneously present both contradictory facts as active.
    facts = storage.load_json_list("t", "facts")
    assert len(facts) == 1
    assert facts[0]["id"] == first
    assert facts[0]["status"] == "active"


def test_add_fact_with_unknown_contradicts_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", "unknown_fact_id",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown contradicts target" in result.stderr
