from causal_graph import storage
from tests.cli_support import run_cli as _run


def test_add_fact_requires_known_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "x", "--evidence-id", "missing",
        "--confidence", "verified",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown evidence id" in result.stderr


def test_add_fact_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", "unknown_fact_id",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown contradicts target" in result.stderr
