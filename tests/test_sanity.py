# tests/test_sanity.py
from causal_graph.cli import current_agent_id


def test_current_agent_id_defaults(monkeypatch):
    monkeypatch.delenv("CAUSAL_GRAPH_AGENT_ID", raising=False)
    assert current_agent_id() == "agent"


def test_current_agent_id_from_env(monkeypatch):
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "custom")
    assert current_agent_id() == "custom"
