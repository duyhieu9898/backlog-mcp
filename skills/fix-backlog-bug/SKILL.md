---
name: fix-backlog-bug
description: Use when the user asks to fix a Backlog bug given its issue key or link (e.g. "backlog fix OOP-123", "sửa bug OOP-123") and the fix should end with the bug resolved in Backlog.
---

# Fix a Backlog bug

Take one Backlog bug from report to resolved. The Backlog MCP reads and resolves the bug; this skill sets the order, the stops, and everything outside Backlog (code, tests, git).

**The request is the permission.** "backlog fix OOP-123" asks for the whole flow: fix, test, commit, push and resolve. Do not stop after the code change to ask whether to commit; stop only at the stops below.

## Steps

1. **Locate the repo.** In a git repo whose `.backlog-project.json` `project_key` equals the key prefix (OOP-123 → OOP): work here. Another project: stop and ask. Not in a repo: ask for the repo path.
2. **Check git.** Uncommitted changes to tracked files (`git status --porcelain --untracked-files=no` not empty) → stop and ask; never mix the user's changes into the fix. Untracked files such as `.backlog-project.json` are fine. On `main`/`master`, or no upstream (`git rev-parse --abbrev-ref @{u}` fails) → you may fix the code, but stop before committing and say which branch blocked it.
3. **Read the bug:** `get_issue(issue_key)`. Work from steps_to_reproduce, actual, expected. Attachments are listed, not fetched: if one looks essential, tell the user.
4. **Fix the cause** with the smallest change. A regression test in the existing test suite is welcome; do not set up testing where the repo has none.
5. **Run the repo's tests.** Command from CLAUDE.md / AGENTS.md / README, else `package.json` `test`, `Makefile` `test`, `python -m pytest`, `go test ./...`. No test command → skip and say so in the report.
6. **Any failing test → stop.** No commit, no push, no resolve; report the failing tests.
7. **Commit only the fix:** stage the files you changed by path (`git add <paths>`, never `git add -A`), then commit `fix(OOP-123): <what changed, short>` (commitlint).
8. **Push** the current branch with `git push`; never `--force`. Rejected → stop, no resolve.
9. **Resolve:** `resolve_bug(issue_key, mode="apply", commit=<pushed short sha>, fix_description=<text after "fix(OOP-123): ">)`.
10. **Report** the fix, the test result, the commit, and resolve_bug's changes and warnings.

## Stop, don't resolve

| Thought | Reality |
|---|---|
| "That test was already failing before my change and is unrelated" | Any red test blocks commit and resolve: the tester would get a broken build. Report it and stop. |
| "I'm on main, it's a one-line fix" | No commit on main/master. Stop and say so. |
| "The push failed, but the commit exists" | Resolve would send the tester to code that is not on the remote. |
