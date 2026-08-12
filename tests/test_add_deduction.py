from causal_graph import storage
from tests.cli_support import run_cli as _run


def test_add_deduction_rejects_unknown_support(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", "fact:missing",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown supporting node" in result.stderr


def test_add_deduction_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "A and B together imply C",
        "--supports", f"fact:{f1},fact:{f2}", "--logic-note", "conjunction",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    ded_id = result.stdout.strip()
    deds = storage.load_json_list("t", "deductions")
    assert deds[0]["id"] == ded_id
    assert deds[0]["supporting_fact_ids"] == [f1, f2]
    assert deds[0]["status"] == "active"


def test_add_deduction_rejects_empty_supports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", "",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "at least one fact or deduction" in result.stderr


def test_add_deduction_rejects_inactive_supporting_fact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    _run("revise_fact.py", ["--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)

    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", f"fact:{f1}",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "not active" in result.stderr
