import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

MANIFESTS = [
    REPO_ROOT / ".claude-plugin" / "plugin.json",
    REPO_ROOT / ".codex-plugin" / "plugin.json",
    REPO_ROOT / ".cursor-plugin" / "plugin.json",
]

SKILL_NAMES = ("causal-graph-research", "aha-opportunity-scout")


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
        for skill_name in SKILL_NAMES:
            assert (skills_dir / skill_name / "SKILL.md").is_file()


def test_agent_discovery_links_point_at_the_shared_skill_sources():
    for discovery_root in (REPO_ROOT / ".agents" / "skills",
                           REPO_ROOT / ".claude" / "skills"):
        for skill_name in SKILL_NAMES:
            skill_link = discovery_root / skill_name / "SKILL.md"
            assert skill_link.is_symlink()
            assert skill_link.resolve() == REPO_ROOT / "skills" / skill_name / "SKILL.md"
