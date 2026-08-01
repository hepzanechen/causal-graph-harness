import subprocess
import sys

from causal_graph import storage


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "scripts/add_evidence.py", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_add_evidence_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts").mkdir()
    import shutil, pathlib
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(repo_root / "scripts" / "add_evidence.py", tmp_path / "scripts" / "add_evidence.py")

    result = _run(
        ["--topic", "t", "--adapter", "human", "--content", "saw it happen",
         "--source-ref", "conversation:2026-08-01"],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    ev_id = result.stdout.strip()
    records = storage.load_json_list("t", "evidence")
    assert len(records) == 1
    assert records[0]["id"] == ev_id
    assert records[0]["source_adapter"] == "human"
    assert records[0]["content"] == "saw it happen"
