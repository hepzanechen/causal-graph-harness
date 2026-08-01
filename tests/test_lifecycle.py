from causal_graph import storage
from causal_graph.lifecycle import propagate_stale


def test_propagate_stale_marks_downstream_deduction_and_edge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.save_json_list("t", "facts", [{"id": "f1", "status": "active"}, {"id": "f2", "status": "active"}])
    storage.save_json_list("t", "deductions", [
        {"id": "d1", "supporting_fact_ids": ["f1"], "supporting_deduction_ids": [], "status": "active"},
    ])
    storage.save_json_list("t", "causal_edges", [
        {"id": "e1", "from_node": "deduction:d1", "to_node": "fact:f2", "status": "active"},
    ])

    writes = propagate_stale("t", "fact:f1")

    by_id = {r["id"]: r for _, r in writes}
    assert by_id["d1"]["status"] == "stale"
    assert by_id["e1"]["status"] == "stale"


def test_propagate_stale_edge_ref_has_no_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert propagate_stale("t", "edge:e1") == []
