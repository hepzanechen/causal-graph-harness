from causal_graph import storage
from tests.cli_support import run_cli as _run


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
