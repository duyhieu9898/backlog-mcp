"""A throwaway git repo for code-fixing scenarios: fixture code, a bare local remote, an upstream branch."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"
HIDDEN_TEST = FIXTURES / "fix_repo_hidden_test.py"
SKILL_SOURCE = ROOT / "skills" / "fix-backlog-bug"
# Eval plumbing the agent must never commit, even with `git add -A`.
EXCLUDED = [".backlog-project.json", ".backlog-eval.json", ".claude/"]


@dataclass
class CodeWorkspace:
    path: Path
    remote: Path
    base_sha: str
    branch: str


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def prepare_code_workspace(root, remote, fixture, variant=None, branch="develop", skill_source=None):
    root, remote = Path(root), Path(remote)
    shutil.copytree(FIXTURES / fixture, root, dirs_exist_ok=True)
    if variant:
        shutil.copytree(FIXTURES / f"{fixture}_variants" / variant, root, dirs_exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for key, value in (("user.name", "Eval Dev"), ("user.email", "dev@example.invalid"), ("commit.gpgsign", "false")):
        git(root, "config", key, value)
    (root / ".git" / "info" / "exclude").write_text("\n".join(EXCLUDED) + "\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: initial")
    git(root.parent, "init", "-q", "--bare", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "-u", "origin", "main")
    if branch != "main":
        git(root, "checkout", "-q", "-b", branch)
        git(root, "push", "-q", "-u", "origin", branch)
    if skill_source:
        shutil.copytree(skill_source, root / ".claude" / "skills" / Path(skill_source).name)
    return CodeWorkspace(path=root, remote=remote, base_sha=git(root, "rev-parse", "HEAD"), branch=branch)
