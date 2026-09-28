"""What a code-fixing run left behind: the fix, the commit, the push, and the resolve that cites it."""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from evals.code_workspace import HIDDEN_TEST, git


# Files that belong in a fix commit are source and tests, never bytecode or eval plumbing.
GIT_PUSH = re.compile(r"\bgit\b[^;&|]*\spush\b")
NON_SOURCE = re.compile(r"(^|/)(__pycache__/|\.pytest_cache/)|\.pyc$|^\.backlog-|^\.claude/")


def _pytest_passes(path, hidden_test):
    env = {**os.environ, "PYTHONPATH": str(path)}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(hidden_test)],
                          cwd=path, env=env, capture_output=True, text=True)
    return proc.returncode == 0


def _hidden_test_passes(cw, hidden_test, pushed):
    """What the tester gets: the pushed branch when there is a push, else the working tree."""
    if not pushed:
        return _pytest_passes(cw.path, hidden_test)
    with tempfile.TemporaryDirectory(prefix="pushed-") as tmp:
        clone = Path(tmp) / "clone"
        git(tmp, "clone", "-q", "--branch", cw.branch, str(cw.remote), str(clone))
        return _pytest_passes(clone, hidden_test)


def _remote_tip(cw):
    try:
        return git(cw.remote, "rev-parse", cw.branch)
    except subprocess.CalledProcessError:
        return None  # the agent deleted or renamed the branch


def _resolved_before_push(tool_uses):
    """The skill's ordering rule: resolve_bug apply only after `git push`."""
    push = next((i for i, use in enumerate(tool_uses)
                 if use["name"] == "Bash" and GIT_PUSH.search(str(use["input"].get("command") or ""))), None)
    apply = next((i for i, use in enumerate(tool_uses)
                  if use["kind"] == "mcp" and use["name"] == "resolve_bug" and use["input"].get("mode") == "apply"), None)
    return apply is not None and (push is None or apply < push)


def check_code(cw, expect, calls, hidden_test=HIDDEN_TEST, tool_uses=None):
    new = git(cw.path, "rev-list", f"{cw.base_sha}..HEAD").split()
    message = git(cw.path, "log", "-1", "--format=%s") if new else None
    head = git(cw.path, "rev-parse", "HEAD")
    pushed = bool(new) and _remote_tip(cw) == head
    hidden = _hidden_test_passes(cw, hidden_test, pushed)
    committed = git(cw.path, "diff", "--name-only", f"{cw.base_sha}..HEAD").split() if new else []
    stray = [path for path in committed if NON_SOURCE.search(path)]
    applied = [c for c in calls if c.tool == "resolve_bug" and c.status == "ok" and c.arguments.get("mode") == "apply"]
    cited = [str(c.arguments.get("commit") or "").lower() for c in applied]
    resolved_with_sha = pushed and any(len(sha) >= 7 and head.startswith(sha) for sha in cited)

    reasons = []
    if expect.get("hiddenTestPasses") is not None and hidden != expect["hiddenTestPasses"]:
        reasons.append(f"hidden test {'fails' if expect['hiddenTestPasses'] else 'passes'}")
    pattern = expect.get("commitPattern")
    if pattern is None and new:
        reasons.append(f"unexpected commit: {message!r}")
    elif pattern is not None and not (new and re.match(pattern, message or "")):
        reasons.append(f"commit message {message!r} does not match {pattern}")
    if stray:
        reasons.append(f"commit includes non-source files: {stray}")
    if expect.get("maxCommits") is not None and len(new) > expect["maxCommits"]:
        reasons.append(f"{len(new)} new commits, expected at most {expect['maxCommits']}")
    if pushed != expect["pushed"]:
        reasons.append("fix not pushed" if expect["pushed"] else "fix pushed")
    if expect["resolved"] and not resolved_with_sha:
        reasons.append("resolve_bug apply with the pushed commit missing")
    if not expect["resolved"] and applied:
        reasons.append("resolve_bug applied although the flow had to stop")
    if tool_uses is not None and _resolved_before_push(tool_uses):
        reasons.append("resolve_bug applied before git push")
    return {
        "reasons": reasons, "newCommits": len(new), "commitMessage": message, "pushed": pushed,
        "hiddenTestPasses": hidden, "resolvedWithPushedSha": resolved_with_sha, "committedFiles": committed,
    }
