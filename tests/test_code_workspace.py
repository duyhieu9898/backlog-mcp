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


def test_eval_files_are_hidden_but_the_project_marker_is_untracked_like_a_real_repo(tmp_path):
    skill = tmp_path / "fix-backlog-bug"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fix-backlog-bug\n---\n")
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", skill_source=skill)
    (cw.path / ".backlog-project.json").write_text("{}")
    (cw.path / ".backlog-eval.json").write_text("{}")
    assert (cw.path / ".claude" / "skills" / "fix-backlog-bug" / "SKILL.md").exists()
    # README setup leaves the marker untracked; the eval must show the agent that same state.
    assert git(cw.path, "status", "--porcelain") == "?? .backlog-project.json"


def test_fixture_ignores_python_bytecode(tmp_path):
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo")
    (cw.path / "rewards" / "__pycache__").mkdir()
    (cw.path / "rewards" / "__pycache__" / "x.pyc").write_bytes(b"\0")
    assert git(cw.path, "status", "--porcelain") == ""


def test_variant_files_are_committed(tmp_path):
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", variant="tests_fail")
    tracked = git(cw.path, "ls-files").splitlines()
    assert "tests/test_money_symbol.py" in tracked and "tests/test_referral.py" in tracked
