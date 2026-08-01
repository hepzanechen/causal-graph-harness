import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py",
           "update_causal_edge.py", "record_falsification_check.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_edge(tmp_path, prior="0.5"):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", prior,
    ], cwd=tmp_path).stdout.strip()
    return edge, ev


def test_record_falsification_check_appends_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_edge(tmp_path)
    result = _run("record_falsification_check.py", [
        "--topic", "t", "--edge-id", edge,
        "--alternative-hypothesis", "unrelated deploy caused it",
        "--counterevidence-search", "checked deploy logs for the same window",
        "--result", "no correlating deploy found",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["falsification_checks"]) == 1
    assert "no correlating deploy found" in edges[0]["falsification_checks"][0]["counterevidence_search_result"]


def test_falsification_check_unblocks_high_confidence_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.5")

    # Without a falsification check, a strong update is diverted (Task 11 behavior).
    diverted = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert "queued for review" in diverted.stdout

    _run("record_falsification_check.py", [
        "--topic", "t", "--edge-id", edge,
        "--alternative-hypothesis", "alt", "--counterevidence-search", "search", "--result", "null result",
    ], cwd=tmp_path)

    applied = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert applied.returncode == 0, applied.stderr
    assert "queued for review" not in applied.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["updates"]) == 1
