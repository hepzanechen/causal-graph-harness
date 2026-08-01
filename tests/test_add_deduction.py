import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py", "revise_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_add_deduction_rejects_unknown_support(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", "fact:missing",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown supporting node" in result.stderr


def test_add_deduction_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
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
    _copy_scripts(tmp_path)
    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", "",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "at least one fact or deduction" in result.stderr


def test_add_deduction_rejects_inactive_supporting_fact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    _run("revise_fact.py", ["--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "wrong"], cwd=tmp_path)

    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", f"fact:{f1}",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "not active" in result.stderr
