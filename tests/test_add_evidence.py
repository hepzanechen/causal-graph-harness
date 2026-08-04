from causal_graph import storage
from tests.cli_support import run_cli as _run


def test_add_evidence_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "saw it happen",
        "--source-ref", "conversation:2026-08-01",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    ev_id = result.stdout.strip()
    records = storage.load_json_list("t", "evidence")
    assert len(records) == 1
    assert records[0]["id"] == ev_id
    assert records[0]["source_adapter"] == "human"
    assert records[0]["content"] == "saw it happen"
