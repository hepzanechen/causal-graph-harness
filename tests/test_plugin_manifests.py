import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

MANIFESTS = [
    REPO_ROOT / ".claude-plugin" / "plugin.json",
    REPO_ROOT / ".codex-plugin" / "plugin.json",
    REPO_ROOT / ".cursor-plugin" / "plugin.json",
]


def test_all_manifests_are_valid_json_with_required_fields():
    for path in MANIFESTS:
        data = json.loads(path.read_text())
        assert data["name"] == "causal-graph-harness"
        assert data["version"] == "0.1.0"


def test_codex_and_cursor_manifests_point_at_the_shared_skills_dir():
    # A manifest's "skills" path is relative to the plugin bundle root (the
    # repo root the manifest lives at the top of), not to the manifest
    # file's own directory — same convention obra/superpowers uses.
    for path in (REPO_ROOT / ".codex-plugin" / "plugin.json",
                 REPO_ROOT / ".cursor-plugin" / "plugin.json"):
        data = json.loads(path.read_text())
        skills_dir = (REPO_ROOT / data["skills"]).resolve()
        assert skills_dir == REPO_ROOT / "skills"
        assert (skills_dir / "causal-graph-research" / "SKILL.md").is_file()
