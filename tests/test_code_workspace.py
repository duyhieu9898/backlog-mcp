from evals.code_workspace import git, prepare_code_workspace


def test_workspace_is_a_repo_on_the_branch_with_an_upstream(tmp_path):
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", branch="develop")
    assert git(cw.path, "rev-parse", "--abbrev-ref", "HEAD") == "develop"
    assert git(cw.path, "rev-parse", "--abbrev-ref", "@{u}") == "origin/develop"
    assert git(cw.path, "log", "-1", "--format=%s") == "chore: initial"
    assert git(cw.remote, "rev-parse", "develop") == cw.base_sha
    assert git(cw.path, "status", "--porcelain") == ""


def test_main_branch_workspace(tmp_path):
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", branch="main")
    assert git(cw.path, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_markers_and_skill_never_enter_a_commit(tmp_path):
    skill = tmp_path / "fix-backlog-bug"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fix-backlog-bug\n---\n")
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", skill_source=skill)
    (cw.path / ".backlog-project.json").write_text("{}")
    (cw.path / ".backlog-eval.json").write_text("{}")
    assert (cw.path / ".claude" / "skills" / "fix-backlog-bug" / "SKILL.md").exists()
    git(cw.path, "add", "-A")
    assert git(cw.path, "status", "--porcelain") == ""


def test_variant_files_are_committed(tmp_path):
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", variant="tests_fail")
    tracked = git(cw.path, "ls-files").splitlines()
    assert "tests/test_money_symbol.py" in tracked and "tests/test_referral.py" in tracked
