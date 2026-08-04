import os


def current_agent_id() -> str:
    return os.environ.get("CAUSAL_GRAPH_AGENT_ID", "agent")
