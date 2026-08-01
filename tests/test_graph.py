from causal_graph import storage
from causal_graph.graph import downstream_dependents, urgency_tier


def _seed_small_chain(topic):
    storage.save_json_list(topic, "facts", [{"id": "f1"}, {"id": "f2"}])
    storage.save_json_list(topic, "deductions", [
        {"id": "d1", "supporting_fact_ids": ["f1"], "supporting_deduction_ids": []},
    ])
    storage.save_json_list(topic, "causal_edges", [
        {"id": "e1", "from_node": "deduction:d1", "to_node": "fact:f2"},
    ])


def test_downstream_dependents_chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")
    deps = downstream_dependents("t", "fact:f1")
    assert deps == {"deduction:d1", "edge:e1"}


def test_downstream_dependents_leaf_has_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")
    assert downstream_dependents("t", "fact:f2") == set()


def test_urgency_tier_below_floor_is_always_normal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")  # only 3 fact/deduction nodes, well below the 8-node floor
    assert urgency_tier("t", "fact:f1") == "normal"


def test_urgency_tier_above_floor_flags_high_impact_node(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    facts = [{"id": f"f{i}"} for i in range(10)]
    storage.save_json_list("t", "facts", facts)
    # d1 depends on every fact; the rest are independent leaves.
    deductions = [{"id": "d1", "supporting_fact_ids": [f["id"] for f in facts], "supporting_deduction_ids": []}]
    storage.save_json_list("t", "deductions", deductions)
    storage.save_json_list("t", "causal_edges", [])
    assert urgency_tier("t", "fact:f0") == "urgent"
    assert urgency_tier("t", "deduction:d1") == "normal"
