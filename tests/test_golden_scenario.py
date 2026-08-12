from causal_graph import storage
from tests.cli_support import run_cli as _run_raw


def _run(script, args, cwd):
    result = _run_raw(script, args, cwd)
    assert result.returncode == 0, f"{script} {args} failed: {result.stderr}"
    return result.stdout.strip()


def test_golden_scenario_two_facts_one_deduction_one_edge_two_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ev1 = _run("add_evidence.py", [
        "--topic", "etl", "--adapter", "internal_db",
        "--content", "ETL pod OOM-killed at 02:14 UTC", "--source-ref", "k8s-events/etl-worker-7",
    ], tmp_path)
    ev2 = _run("add_evidence.py", [
        "--topic", "etl", "--adapter", "codebase",
        "--content", "memory limit cut 4Gi to 2Gi in PR #482", "--source-ref", "deployment.yaml:12",
    ], tmp_path)

    f1 = _run("add_fact.py", [
        "--topic", "etl", "--statement", "ETL job OOM-killed at 02:14 UTC",
        "--evidence-id", ev1, "--confidence", "verified",
    ], tmp_path)
    f2 = _run("add_fact.py", [
        "--topic", "etl", "--statement", "Memory limit reduced 4Gi to 2Gi",
        "--evidence-id", ev2, "--confidence", "verified",
    ], tmp_path)

    d1 = _run("add_deduction.py", [
        "--topic", "etl", "--claim", "Memory headroom shrank",
        "--supports", f"fact:{f2}", "--logic-note", "limit halved",
    ], tmp_path)

    e1 = _run("propose_causal_edge.py", [
        "--topic", "etl", "--from", f"deduction:{d1}", "--to", f"fact:{f1}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], tmp_path)

    _run("update_causal_edge.py", [
        "--topic", "etl", "--edge-id", e1, "--evidence-id", ev1, "--likelihood-ratio", "3.0",
    ], tmp_path)
    _run("update_causal_edge.py", [
        "--topic", "etl", "--edge-id", e1, "--evidence-id", ev2, "--likelihood-ratio", "2.0",
    ], tmp_path)

    facts = storage.load_json_list("etl", "facts")
    deductions = storage.load_json_list("etl", "deductions")
    edges = storage.load_json_list("etl", "causal_edges")
    audit = storage.read_audit("etl")

    assert len(facts) == 2
    assert len(deductions) == 1
    assert len(edges) == 1
    assert len(edges[0]["updates"]) == 2
    assert 0.3 < edges[0]["posterior"] < 1.0
    assert len(audit) == 8  # 2 add_evidence + 2 add_fact + 1 add_deduction + 1 propose_causal_edge + 2 update_causal_edge
