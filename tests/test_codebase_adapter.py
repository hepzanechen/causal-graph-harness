from adapters.codebase_adapter import CodebaseAdapter


def test_codebase_adapter_finds_matching_line(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("first line\nmemory limit reduced to 2Gi\nlast line\n")
    adapter = CodebaseAdapter(root=str(tmp_path))
    results = adapter.fetch("memory limit")
    assert len(results) == 1
    assert "memory limit reduced" in results[0].content
    assert results[0].source_ref.endswith(":2")


def test_codebase_adapter_skips_git_dir(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_text("memory limit reduced")
    adapter = CodebaseAdapter(root=str(tmp_path))
    assert adapter.fetch("memory limit") == []


def test_codebase_adapter_no_match_returns_empty(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing relevant here")
    adapter = CodebaseAdapter(root=str(tmp_path))
    assert adapter.fetch("memory limit") == []
