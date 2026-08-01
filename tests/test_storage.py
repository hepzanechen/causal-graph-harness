import json

from causal_graph import storage
from causal_graph.topic import path_for


def test_upsert_inserts_and_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.upsert("t", "facts", {"id": "f1", "statement": "a"})
    storage.upsert("t", "facts", {"id": "f1", "statement": "b"})
    records = storage.load_json_list("t", "facts")
    assert records == [{"id": "f1", "statement": "b"}]


def test_upsert_delete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.upsert("t", "facts", {"id": "f1", "statement": "a"})
    storage.upsert("t", "facts", {"id": "f1", "_delete": True})
    assert storage.load_json_list("t", "facts") == []


def test_commit_mutation_writes_audit_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entry = storage.commit_mutation(
        "t", "agent-1", "add_fact.py", {"statement": "x"},
        [("facts", {"id": "f1", "statement": "x"})],
    )
    assert entry["agent_id"] == "agent-1"
    assert entry["script"] == "add_fact.py"
    assert storage.load_json_list("t", "facts") == [{"id": "f1", "statement": "x"}]
    audit = storage.read_audit("t")
    assert len(audit) == 1
    assert audit[0]["result"]["writes"][0]["record"]["id"] == "f1"


def test_repair_replays_unapplied_audit_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.commit_mutation(
        "t", "agent-1", "add_fact.py", {}, [("facts", {"id": "f1", "statement": "x"})],
    )
    # Simulate a crash: audit entry exists but snapshot was never written and
    # the meta pointer was never advanced.
    storage.save_json_list("t", "facts", [])
    meta_path = path_for("t", "meta")
    meta = json.loads(meta_path.read_text())
    meta["applied_through"] = 0
    meta_path.write_text(json.dumps(meta))

    repaired = storage.repair("t")

    assert repaired == 1
    assert storage.load_json_list("t", "facts") == [{"id": "f1", "statement": "x"}]


def test_prepare_creates_dir_and_repairs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.prepare("t")
    assert path_for("t", "facts").parent.is_dir()
