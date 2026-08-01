import time
from pathlib import Path

from causal_graph.topic import graph_dir, ensure_graph_dir, path_for
from causal_graph.lock import topic_lock


def test_graph_dir_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = ensure_graph_dir("my-topic")
    assert d == Path("research/my-topic/graph")
    assert d.is_dir()


def test_path_for_known_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert path_for("t", "facts").name == "facts.json"
    assert path_for("t", "audit_log").name == "audit_log.jsonl"


def test_topic_lock_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    order = []
    with topic_lock("t"):
        order.append("first-acquired")
    with topic_lock("t"):
        order.append("second-acquired")
    assert order == ["first-acquired", "second-acquired"]
