# Skill `fix-backlog-bug` + eval sửa code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harness eval chạy được agent sửa code thật (repo mẫu, Backlog giả, remote git cục bộ), đo baseline không skill, rồi viết và kiểm skill `fix-backlog-bug`.

**Architecture:** Kịch bản có trường `code` → harness chép repo mẫu vào workspace tạm, dựng git + remote bare, cho agent `claude` quyền Edit/Write và Bash giới hạn (`git`, `pytest`), tuỳ chọn chép skill vào `.claude/skills/`. Grader thêm kiểm tra phía code (test ẩn, commit, push, `resolve_bug` với SHA đã push). Skill là một file Markdown, viết sau baseline.

**Tech Stack:** Python 3.12, pytest, git CLI, `claude -p` stream-json, harness `evals/` hiện có.

**Spec:** `docs/superpowers/specs/2026-09-28-fix-backlog-bug-skill-design.md`

## Global Constraints

- MCP (`backlog_mcp/`, `backlog_tool/` ngoài grader, `workflows/`) không đổi; skill chỉ dùng 8 tool hiện có.
- Commit message trong skill: `fix(OOP-12345): <mô tả ngắn>` (commitlint, scope = key bug).
- Skill: `resolve_bug(mode="apply", commit=<sha đã push>, fix_description=<mô tả ngắn của commit>)` chỉ sau push thành công.
- Git: không `--force`; `main`/`master` hoặc không upstream → dừng trước commit.
- Test fail → không commit, không push, không resolve.
- Eval chỉ agent `claude`, model `opus`; chạy bằng `uv run --extra dev python -m evals.run …` (cần pytest trong env).
- Cô lập: Backlog giả, env bỏ `BACKLOG_*`, key `OOP-9xxxxx`, remote là thư mục bare tạm; không dùng `--dangerously-skip-permissions`.
- Kịch bản code không thuộc `--scenario all`; chạy bằng `--scenario code` hoặc id.
- Trong lúc eval chạy không sửa code repo (server MCP của eval chạy từ thư mục repo).
- Mọi commit kết thúc bằng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; commit thẳng `main` rồi push.

## Review Focus

- Agent `git add -A` → marker `.backlog-*.json` hoặc `.claude/` lọt vào commit: phải bị `.git/info/exclude` chặn (Task 3 test).
- Agent tạo nhiều commit hoặc commit không phải ở HEAD cuối: grader xét commit mới nhất sau "chore: initial" và số commit mới (Task 4 test).
- Agent truyền `commit` là SHA đầy đủ, SHA ngắn 7 ký tự, hoặc SHA không khớp: chỉ tiền tố ≥7 của HEAD đã push mới tính (Task 4 test).
- Agent chạy `resolve_bug` preview (không apply) trong kịch bản phải dừng: không tính là resolve (Task 4 test).
- Fixture biến thể `tests_fail` đè file lên fixture gốc chứ không xoá: test gốc vẫn còn và pass (Task 2 test).

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `evals/fixtures/fix_repo/…` | Repo mẫu Python: bug referral reward, test sẵn có pass |
| `evals/fixtures/fix_repo_variants/tests_fail/tests/test_money_symbol.py` | Test hỏng sẵn, không liên quan |
| `evals/fixtures/fix_repo_hidden_test.py` | Test ẩn xác nhận bug đã sửa |
| `evals/fake_backlog.py` (sửa) | Trạng thái `fix_code`: thêm bug `OOP-912900` |
| `evals/code_workspace.py` (mới) | Dựng workspace git + remote bare + marker exclude + chép skill |
| `evals/code_checks.py` (mới) | Kiểm test ẩn, commit, push, resolve với SHA đã push |
| `backlog_tool/telemetry_grader.py` (sửa) | `allowExtraCalls` |
| `evals/agents.py` (sửa) | `claude_command(..., allow_code=False)` |
| `evals/run.py` (sửa) | Chọn kịch bản, `--skill`, nhánh code trong `run_one`/`grade_run` |
| `evals/scenarios.json` (sửa) | 3 kịch bản code |
| `skills/fix-backlog-bug/SKILL.md` (mới) | Skill |
| `docs/telemetry.md` (sửa) | Mục Eval: chế độ sửa code |

---

### Task 1: Backlog giả — trạng thái `fix_code` với bug `OOP-912900`

**Files:**
- Modify: `evals/fake_backlog.py` (hàm `build_issues`, thêm `_code_bug`)
- Test: `tests/test_fake_backlog.py`

**Interfaces:**
- Produces: `FakeBacklog(state="fix_code", source=...)` phục vụ `OOP-912900` (Bug, Open, assignee = `ME`, createdUser = `REPORTER`, Detected Role Tester, trường resolve rỗng). `CODE_BUG_KEY = "OOP-912900"`.

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_fake_backlog.py`:

```python
from evals.fake_backlog import CODE_BUG_KEY, build_issues


def test_fix_code_state_serves_the_open_code_bug():
    issues = build_issues(state="fix_code", source="synthetic")
    bug = issues[CODE_BUG_KEY]
    assert bug["status"]["name"] == "Open"
    assert bug["assignee"]["id"] == 778617
    assert "Referral" in bug["summary"]
    assert "**Expected:**" in bug["description"]
    role = next(f for f in bug["customFields"] if f["name"] == "Detected Role")
    assert role["value"]["name"] == "Tester"


def test_code_bug_only_exists_in_fix_code_state():
    assert CODE_BUG_KEY not in build_issues(state="default", source="synthetic")
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_fake_backlog.py -q -k code`
Expected: FAIL `ImportError: cannot import name 'CODE_BUG_KEY'`

- [ ] **Step 3: Cài đặt**

Trong `evals/fake_backlog.py`, sau `RESOLVE_FIELDS = …` thêm:

```python
CODE_BUG_KEY = "OOP-912900"
CODE_BUG_DESCRIPTION = (
    "**Environment:** DEV\n\n"
    " **Pre-Condition:** \n- User A giới thiệu User B\n\n"
    " **Steps to reproduce:** \n"
    "1. Admin tặng miễn phí 1 NFT (giá niêm yết 500.000 ₫) cho User B\n"
    "2. Xem Referral Reward của User A\n\n"
    "**Actual:** \nUser A nhận 50.000 ₫ Referral Reward\n\n"
    "**Expected:** \nNFT được tặng miễn phí (is_gift) không tính Referral Reward (0 ₫); "
    "đơn mua bình thường vẫn nhận 10%\n\n"
    " **Evidence:** \n-"
)


def _code_bug():
    """The bug the code-fixing scenarios fix: it lives in evals/fixtures/fix_repo."""
    with open(BASE_FIXTURE, encoding="utf-8") as handle:
        issue = json.load(handle)
    number = int(CODE_BUG_KEY.split("-")[1])
    issue.update({
        "id": number, "keyId": number, "issueKey": CODE_BUG_KEY,
        "summary": "[OOP-912601][Bug][User] Referral: NFT được tặng miễn phí vẫn tính Referral Reward",
        "description": CODE_BUG_DESCRIPTION,
        "status": {**issue["status"], "id": 1, "name": "Open"},
        "assignee": {**issue["assignee"], **ME}, "createdUser": {**issue["createdUser"], **REPORTER},
        "startDate": None, "dueDate": None, "estimatedHours": None, "actualHours": None, "attachments": [],
    })
    for field in issue["customFields"]:
        if field["name"] in RESOLVE_FIELDS:
            field["value"] = None
        if field["name"] == "Detected Role":
            field["value"] = {"id": 2, "name": "Tester"}
    return issue
```

Cuối `build_issues`, ngay trước `return issues`:

```python
    if state == "fix_code":
        issues[CODE_BUG_KEY] = _code_bug()
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `uv run --extra dev pytest tests/test_fake_backlog.py -q`
Expected: PASS (cả test cũ)

- [ ] **Step 5: Commit**

```bash
git add evals/fake_backlog.py tests/test_fake_backlog.py
git commit -m "Serve a code-fixing bug in the fake backend's fix_code state"
```

---

### Task 2: Repo mẫu, biến thể `tests_fail`, test ẩn

**Files:**
- Create: `evals/fixtures/fix_repo/README.md`, `evals/fixtures/fix_repo/pyproject.toml`, `evals/fixtures/fix_repo/rewards/__init__.py`, `evals/fixtures/fix_repo/rewards/referral.py`, `evals/fixtures/fix_repo/rewards/money.py`, `evals/fixtures/fix_repo/tests/test_referral.py`, `evals/fixtures/fix_repo/tests/test_money.py`
- Create: `evals/fixtures/fix_repo_variants/tests_fail/tests/test_money_symbol.py`
- Create: `evals/fixtures/fix_repo_hidden_test.py`
- Test: `tests/test_fix_fixture.py`

**Interfaces:**
- Produces: `FIXTURES = ROOT/evals/fixtures`; fixture `fix_repo`, biến thể `tests_fail`, test ẩn `fix_repo_hidden_test.py` (import `rewards.referral`).

- [ ] **Step 1: Viết test fail**

`tests/test_fix_fixture.py`:

```python
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _pytest(cwd, *targets):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets],
                          cwd=cwd, capture_output=True, text=True, env={"PYTHONPATH": str(cwd), "PATH": ""}).returncode


def _copy(tmp_path, variant=None):
    shutil.copytree(FIXTURES / "fix_repo", tmp_path / "repo")
    if variant:
        shutil.copytree(FIXTURES / "fix_repo_variants" / variant, tmp_path / "repo", dirs_exist_ok=True)
    return tmp_path / "repo"


def test_fixture_tests_pass_but_hidden_test_catches_the_bug(tmp_path):
    repo = _copy(tmp_path)
    assert _pytest(repo) == 0
    assert _pytest(repo, str(FIXTURES / "fix_repo_hidden_test.py")) != 0


def test_tests_fail_variant_adds_a_failing_test_and_keeps_the_rest(tmp_path):
    repo = _copy(tmp_path, "tests_fail")
    assert (repo / "tests" / "test_referral.py").exists()
    assert _pytest(repo, "tests/test_referral.py", "tests/test_money.py") == 0
    assert _pytest(repo) != 0


def test_fixing_the_bug_makes_the_hidden_test_pass(tmp_path):
    repo = _copy(tmp_path)
    source = repo / "rewards" / "referral.py"
    source.write_text(source.read_text().replace(
        "    return round(order.price * REFERRAL_RATE)",
        "    if order.is_gift:\n        return 0\n    return round(order.price * REFERRAL_RATE)"))
    assert _pytest(repo, str(FIXTURES / "fix_repo_hidden_test.py")) == 0
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_fix_fixture.py -q`
Expected: FAIL (`FileNotFoundError` — chưa có fixture)

- [ ] **Step 3: Tạo fixture**

`evals/fixtures/fix_repo/README.md`:

```markdown
# rewards

Referral rewards for NFT orders.

Run tests: `python -m pytest -q`
```

`evals/fixtures/fix_repo/pyproject.toml`:

```toml
[project]
name = "rewards"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`evals/fixtures/fix_repo/rewards/__init__.py`: file rỗng.

`evals/fixtures/fix_repo/rewards/referral.py`:

```python
from dataclasses import dataclass

REFERRAL_RATE = 0.10


@dataclass
class Order:
    price: int
    is_gift: bool = False


def referral_reward(order: Order) -> int:
    """Reward paid to the buyer's referrer, in VND."""
    return round(order.price * REFERRAL_RATE)
```

`evals/fixtures/fix_repo/rewards/money.py`:

```python
def format_vnd(amount: int) -> str:
    return f"{amount:,} ₫".replace(",", ".")
```

`evals/fixtures/fix_repo/tests/test_referral.py`:

```python
from rewards.referral import Order, referral_reward


def test_reward_is_ten_percent_of_price():
    assert referral_reward(Order(price=200_000)) == 20_000
```

`evals/fixtures/fix_repo/tests/test_money.py`:

```python
from rewards.money import format_vnd


def test_thousands_use_dots():
    assert format_vnd(1000) == "1.000 ₫"
```

`evals/fixtures/fix_repo_variants/tests_fail/tests/test_money_symbol.py`:

```python
from rewards.money import format_vnd


def test_symbol_comes_first():
    # The new design puts the currency symbol first; money.py has not caught up yet.
    assert format_vnd(1000) == "₫1.000"
```

`evals/fixtures/fix_repo_hidden_test.py`:

```python
from rewards.referral import Order, referral_reward


def test_gift_nft_earns_no_referral_reward():
    assert referral_reward(Order(price=500_000, is_gift=True)) == 0


def test_paid_order_still_earns_ten_percent():
    assert referral_reward(Order(price=500_000)) == 50_000
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `uv run --extra dev pytest tests/test_fix_fixture.py -q`
Expected: PASS (3 test). `pyproject.toml` gốc có `testpaths = ["tests"]` nên `uv run --extra dev pytest -q` không thu thập test trong `evals/fixtures`.

- [ ] **Step 5: Commit**

```bash
git add evals/fixtures tests/test_fix_fixture.py
git commit -m "Add the referral-reward repo fixture and its hidden test"
```

---

### Task 3: Dựng workspace git cho kịch bản code

**Files:**
- Create: `evals/code_workspace.py`
- Test: `tests/test_code_workspace.py`

**Interfaces:**
- Consumes: fixture Task 2.
- Produces:
  - `FIXTURES: Path`, `HIDDEN_TEST: Path`, `SKILL_SOURCE: Path` (`ROOT/skills/fix-backlog-bug`)
  - `@dataclass CodeWorkspace(path: Path, remote: Path, base_sha: str, branch: str)`
  - `git(cwd, *args) -> str`
  - `prepare_code_workspace(root: Path, remote: Path, fixture: str, variant: str | None = None, branch: str = "develop", skill_source: Path | None = None) -> CodeWorkspace`

- [ ] **Step 1: Viết test fail**

`tests/test_code_workspace.py`:

```python
import subprocess
from pathlib import Path

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
    skill = tmp_path / "skill"
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
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_code_workspace.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'evals.code_workspace'`

- [ ] **Step 3: Cài đặt**

`evals/code_workspace.py`:

```python
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
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `uv run --extra dev pytest tests/test_code_workspace.py -q`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add evals/code_workspace.py tests/test_code_workspace.py
git commit -m "Build a git workspace with a bare remote for code-fixing scenarios"
```

---

### Task 4: Kiểm tra phía code

**Files:**
- Create: `evals/code_checks.py`
- Test: `tests/test_code_checks.py`

**Interfaces:**
- Consumes: `CodeWorkspace`, `git`, `HIDDEN_TEST` (Task 3); call objects có `.tool`, `.arguments`, `.status` (`backlog_tool.telemetry_store` Call).
- Produces: `check_code(cw: CodeWorkspace, expect: dict, calls: list, hidden_test: Path = HIDDEN_TEST) -> dict` với khoá `reasons: list[str]`, `newCommits: int`, `commitMessage: str | None`, `pushed: bool`, `hiddenTestPasses: bool`, `resolvedWithPushedSha: bool`. `expect` = `{"hiddenTestPasses": bool | None, "commitPattern": str | None, "pushed": bool, "resolved": bool}`.

- [ ] **Step 1: Viết test fail**

`tests/test_code_checks.py`:

```python
from types import SimpleNamespace

from evals.code_checks import check_code
from evals.code_workspace import git, prepare_code_workspace

FIXED = "    if order.is_gift:\n        return 0\n    return round(order.price * REFERRAL_RATE)"
DONE = {"hiddenTestPasses": True, "commitPattern": r"^fix\(OOP-912900\): ", "pushed": True, "resolved": True}
STOPPED = {"hiddenTestPasses": None, "commitPattern": None, "pushed": False, "resolved": False}


def call(tool, **arguments):
    return SimpleNamespace(tool=tool, arguments=arguments, status="ok")


def fix_and_commit(cw, message="fix(OOP-912900): skip referral reward for gift NFTs", push=True):
    source = cw.path / "rewards" / "referral.py"
    source.write_text(source.read_text().replace("    return round(order.price * REFERRAL_RATE)", FIXED))
    git(cw.path, "commit", "-q", "-am", message)
    if push:
        git(cw.path, "push", "-q")
    return git(cw.path, "rev-parse", "HEAD")


def workspace(tmp_path, branch="develop"):
    return prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", branch=branch)


def test_full_flow_passes(tmp_path):
    cw = workspace(tmp_path)
    sha = fix_and_commit(cw)
    result = check_code(cw, DONE, [call("get_issue", issue_key="OOP-912900"),
                                   call("resolve_bug", issue_key="OOP-912900", mode="apply", commit=sha[:7])])
    assert result["reasons"] == []
    assert result["pushed"] and result["hiddenTestPasses"] and result["resolvedWithPushedSha"]


def test_wrong_or_short_sha_does_not_count(tmp_path):
    cw = workspace(tmp_path)
    fix_and_commit(cw)
    for commit in ("abc1234", "", None):
        result = check_code(cw, DONE, [call("resolve_bug", issue_key="OOP-912900", mode="apply", commit=commit)])
        assert result["resolvedWithPushedSha"] is False
        assert any("resolve_bug" in r for r in result["reasons"])


def test_commit_message_must_match(tmp_path):
    cw = workspace(tmp_path)
    sha = fix_and_commit(cw, message="Fix referral reward")
    result = check_code(cw, DONE, [call("resolve_bug", issue_key="OOP-912900", mode="apply", commit=sha)])
    assert any("does not match" in r for r in result["reasons"])


def test_unpushed_commit_is_not_pushed(tmp_path):
    cw = workspace(tmp_path)
    fix_and_commit(cw, push=False)
    result = check_code(cw, DONE, [])
    assert result["pushed"] is False and result["newCommits"] == 1


def test_stop_scenario_passes_when_nothing_was_committed(tmp_path):
    cw = workspace(tmp_path)
    result = check_code(cw, STOPPED, [call("get_issue", issue_key="OOP-912900"),
                                      call("resolve_bug", issue_key="OOP-912900", mode="preview")])
    assert result["reasons"] == []


def test_stop_scenario_fails_on_commit_push_or_apply(tmp_path):
    cw = workspace(tmp_path)
    sha = fix_and_commit(cw)
    result = check_code(cw, STOPPED, [call("resolve_bug", issue_key="OOP-912900", mode="apply", commit=sha)])
    reasons = " | ".join(result["reasons"])
    assert "unexpected commit" in reasons and "pushed" in reasons and "resolve_bug applied" in reasons
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_code_checks.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'evals.code_checks'`

- [ ] **Step 3: Cài đặt**

`evals/code_checks.py`:

```python
"""What a code-fixing run left behind: the fix, the commit, the push, and the resolve that cites it."""

import os
import re
import subprocess
import sys

from evals.code_workspace import HIDDEN_TEST, git


def _hidden_test_passes(cw, hidden_test):
    env = {**os.environ, "PYTHONPATH": str(cw.path)}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(hidden_test)],
                          cwd=cw.path, env=env, capture_output=True, text=True)
    return proc.returncode == 0


def check_code(cw, expect, calls, hidden_test=HIDDEN_TEST):
    new = git(cw.path, "rev-list", f"{cw.base_sha}..HEAD").split()
    message = git(cw.path, "log", "-1", "--format=%s") if new else None
    head = git(cw.path, "rev-parse", "HEAD")
    pushed = bool(new) and git(cw.remote, "rev-parse", cw.branch) == head
    hidden = _hidden_test_passes(cw, hidden_test)
    applied = [c for c in calls if c.tool == "resolve_bug" and c.status == "ok" and c.arguments.get("mode") == "apply"]
    cited = [str(c.arguments.get("commit") or "") for c in applied]
    resolved_with_sha = pushed and any(len(sha) >= 7 and head.startswith(sha) for sha in cited)

    reasons = []
    if expect.get("hiddenTestPasses") is not None and hidden != expect["hiddenTestPasses"]:
        reasons.append(f"hidden test {'fails' if expect['hiddenTestPasses'] else 'passes'}")
    pattern = expect.get("commitPattern")
    if pattern is None and new:
        reasons.append(f"unexpected commit: {message!r}")
    elif pattern is not None and not (new and re.match(pattern, message or "")):
        reasons.append(f"commit message {message!r} does not match {pattern}")
    if pushed != expect["pushed"]:
        reasons.append("fix not pushed" if expect["pushed"] else "fix pushed")
    if expect["resolved"] and not resolved_with_sha:
        reasons.append("resolve_bug apply with the pushed commit missing")
    if not expect["resolved"] and applied:
        reasons.append("resolve_bug applied although the flow had to stop")
    return {
        "reasons": reasons, "newCommits": len(new), "commitMessage": message, "pushed": pushed,
        "hiddenTestPasses": hidden, "resolvedWithPushedSha": resolved_with_sha,
    }
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `uv run --extra dev pytest tests/test_code_checks.py -q`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add evals/code_checks.py tests/test_code_checks.py
git commit -m "Grade what a code-fixing run left: hidden test, commit, push, cited resolve"
```

---

### Task 5: Kịch bản code, grader `allowExtraCalls`, nối vào harness

**Files:**
- Modify: `backlog_tool/telemetry_grader.py` (hàm `grade`)
- Modify: `evals/agents.py` (`claude_command`)
- Modify: `evals/run.py` (`grade_run`, `run_one`, `main`, `_run_batch`, thêm `select_scenarios`)
- Modify: `evals/scenarios.json`
- Test: `tests/test_telemetry_grader.py`, `tests/test_eval_run.py`

**Interfaces:**
- Consumes: `FakeBacklog(state="fix_code")` (Task 1), `prepare_code_workspace`, `SKILL_SOURCE` (Task 3), `check_code` (Task 4).
- Produces:
  - `grade(expect, ...)` bỏ qua lý do "extra calls" khi `expect.get("allowExtraCalls")`.
  - `claude_command(prompt, model, mcp_config_path, allow_code=False) -> list[str]`; `CLAUDE_CODE_ALLOWED: list[str]`.
  - `select_scenarios(scenarios: list, choice: str) -> list`: `"all"` = kịch bản không có `code`; `"code"` = kịch bản có `code`; còn lại = theo `id`.
  - `run_one(agent, model, scenario, index, timeout_s, workspace=None, source="cassette", skill=False)`.
  - `grade_run(scenario, trace, log_dir, run_id, code_ws=None)`; kết quả có thêm `code` (dict của `check_code`) khi có `code_ws`.
  - CLI `--skill on|off` (mặc định `off`); dòng kết quả có `"skill": bool`.

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_telemetry_grader.py`:

```python
def test_allow_extra_calls_ignores_extras():
    expect = {"calls": [{"tool": "get_issue", "args": {"issue_key": "OOP-912900"}}], "order": "any",
              "forbidden": [], "finalAnswer": None, "allowExtraCalls": True}
    flow = Flow("r", [call("get_issue", {"issue_key": "OOP-912900"}), call("get_bug_rules", {})])
    assert grade(expect, flow)["pass"] is True


def test_code_scenarios_do_not_join_real_prompt_matching():
    scenarios = load_scenarios()
    assert match_prompt("backlog fix OOP-912900", scenarios)[0]["id"] == "fix_context"
```

Thêm vào `tests/test_eval_run.py`:

```python
from evals.agents import claude_command
from evals.run import select_scenarios


def test_select_scenarios_keeps_code_out_of_all():
    scenarios = load_scenarios()
    ids = lambda choice: {s["id"] for s in select_scenarios(scenarios, choice)}
    assert ids("code") == {"fix_code", "fix_code_tests_fail", "fix_code_on_main"}
    assert not ids("all") & ids("code") and "resolve_fixed" in ids("all")
    assert ids("fix_code_on_main") == {"fix_code_on_main"}


def test_claude_command_allows_only_git_and_pytest_bash_for_code():
    plain = claude_command("p", "opus", "/tmp/mcp.json")
    code = claude_command("p", "opus", "/tmp/mcp.json", allow_code=True)
    assert "Bash" in plain[plain.index("--disallowedTools") + 1:]
    assert "--dangerously-skip-permissions" not in code
    denied = code[code.index("--disallowedTools") + 1:code.index("--allowedTools")]
    assert "Bash" not in denied and "Edit" not in denied and "WebFetch" in denied
    allowed = code[code.index("--allowedTools") + 1:]
    assert "Bash(git:*)" in allowed and "Edit" in allowed


def test_grade_run_adds_code_checks(tmp_path, monkeypatch):
    from evals.code_workspace import prepare_code_workspace

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(settings, "LOG_DIR", str(log_dir))
    telemetry.set_eval_tags("run-c", "fix_code_on_main")
    telemetry.log_session_start(backend="fake")
    telemetry.start_call("get_issue", {"issue_key": "OOP-912900"})
    telemetry.finish_call("ok", result={"ok": True}, text="{}", response_bytes=300)
    telemetry.set_eval_tags(None, None)
    cw = prepare_code_workspace(tmp_path / "ws", tmp_path / "remote.git", "fix_repo", branch="main")
    trace = AgentTrace(model="m", final_answer="Đang ở nhánh main nên không commit.", raw_ok=True)
    result = grade_run(scenario("fix_code_on_main"), trace, log_dir, "run-c", code_ws=cw)
    assert result["code"]["newCommits"] == 0 and result["code"]["reasons"] == []
    assert result["pass"] is True
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_telemetry_grader.py tests/test_eval_run.py -q`
Expected: FAIL (`ImportError: cannot import name 'select_scenarios'`, thiếu kịch bản code)

- [ ] **Step 3a: Grader**

Trong `backlog_tool/telemetry_grader.py`, hàm `grade`, thay

```python
    extra = [c.tool for c in remaining]
    if extra:
        reasons.append(f"extra calls: {extra}")
```

bằng

```python
    extra = [c.tool for c in remaining]
    # Code-fixing flows may inspect rules or fields on the way; only the listed calls are required.
    if extra and not expect.get("allowExtraCalls"):
        reasons.append(f"extra calls: {extra}")
```

- [ ] **Step 3b: Kịch bản** — thêm vào cuối mảng `evals/scenarios.json`:

```json
  {
    "id": "fix_code",
    "prompt": "backlog fix {issue}",
    "fixtures": {"issue": "OOP-912900"},
    "fakeState": "fix_code",
    "match": null,
    "code": {"fixture": "fix_repo", "variant": null, "branch": "develop"},
    "expect": {
      "calls": [{"tool": "get_issue", "args": {"issue_key": "{issue}"}},
                {"tool": "resolve_bug", "args": {"issue_key": "{issue}", "mode": "apply"}}],
      "order": "any",
      "allowExtraCalls": true,
      "forbidden": [],
      "finalAnswer": null,
      "code": {"hiddenTestPasses": true, "commitPattern": "^fix\\(OOP-912900\\): ", "pushed": true, "resolved": true}
    },
    "nonMcp": null
  },
  {
    "id": "fix_code_tests_fail",
    "prompt": "backlog fix {issue}",
    "fixtures": {"issue": "OOP-912900"},
    "fakeState": "fix_code",
    "match": null,
    "code": {"fixture": "fix_repo", "variant": "tests_fail", "branch": "develop"},
    "expect": {
      "calls": [{"tool": "get_issue", "args": {"issue_key": "{issue}"}}],
      "order": "any",
      "allowExtraCalls": true,
      "forbidden": [],
      "finalAnswer": {"mustMention": [["fail", "lỗi", "hỏng"]]},
      "code": {"hiddenTestPasses": null, "commitPattern": null, "pushed": false, "resolved": false}
    },
    "nonMcp": null
  },
  {
    "id": "fix_code_on_main",
    "prompt": "backlog fix {issue}",
    "fixtures": {"issue": "OOP-912900"},
    "fakeState": "fix_code",
    "match": null,
    "code": {"fixture": "fix_repo", "variant": null, "branch": "main"},
    "expect": {
      "calls": [{"tool": "get_issue", "args": {"issue_key": "{issue}"}}],
      "order": "any",
      "allowExtraCalls": true,
      "forbidden": [],
      "finalAnswer": {"mustMention": [["main"]]},
      "code": {"hiddenTestPasses": null, "commitPattern": null, "pushed": false, "resolved": false}
    },
    "nonMcp": null
  }
```

- [ ] **Step 3c: Agent** — trong `evals/agents.py`, sau `CLAUDE_DISALLOWED = …`:

```python
# Code-fixing runs may edit files and run git and the repo's tests, nothing else.
CLAUDE_CODE_ALLOWED = ["Read", "Glob", "Grep", "Edit", "Write",
                       "Bash(git:*)", "Bash(python -m pytest:*)", "Bash(python3 -m pytest:*)", "Bash(pytest:*)"]
```

thay `claude_command` bằng:

```python
def claude_command(prompt, model, mcp_config_path, allow_code=False):
    denied = [t for t in CLAUDE_DISALLOWED if not (allow_code and t in ("Bash", "Edit", "Write"))]
    command = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--mcp-config", str(mcp_config_path),
        "--disallowedTools", *denied,
    ]
    if allow_code:
        command += ["--allowedTools", *CLAUDE_CODE_ALLOWED]
    return command
```

- [ ] **Step 3d: Harness** — trong `evals/run.py`:

Import thêm:

```python
from evals.code_checks import check_code
from evals.code_workspace import SKILL_SOURCE, prepare_code_workspace
```

Thêm hàm:

```python
def select_scenarios(scenarios, choice):
    if choice == "all":
        return [s for s in scenarios if not s.get("code")]
    if choice == "code":
        return [s for s in scenarios if s.get("code")]
    return [s for s in scenarios if s["id"] == choice]
```

`grade_run` nhận `code_ws=None`; trước `return result`, sau khối `isolationFailed`:

```python
    if code_ws is not None:
        checks = check_code(code_ws, scenario["expect"]["code"], flow.calls)
        result["code"] = checks
        if checks["reasons"]:
            result["pass"] = False
            result["reasons"] = [*result["reasons"], *checks["reasons"]]
```

`run_one` nhận `skill=False`; trong `with FakeBacklog(...)`, thay khối dựng workspace/command:

```python
                code_ws = None
                if scenario.get("code"):
                    if agent != "claude" or workspace:
                        raise ValueError("code scenarios run with --agent claude and no --workspace")
                    code_ws = prepare_code_workspace(root, Path(tmp) / "remote.git", **scenario["code"],
                                                     skill_source=SKILL_SOURCE if skill else None)
                ws = prepare_workspace(root, scenario, run_id, fake.base_url, log_dir)
                if agent == "claude":
                    command = build_command(scenario["prompt"], model, write_mcp_config(tmp), allow_code=bool(code_ws))
```

(các nhánh `codex`/agy giữ nguyên), gọi `result = grade_run(scenario, trace, log_dir, run_id, code_ws=code_ws)` và thêm `"skill": skill` vào `result.update({...})`.

`main`: thêm `parser.add_argument("--skill", choices=["on", "off"], default="off")`; thay dòng chọn kịch bản bằng
`scenarios = [render_scenario(s) for s in select_scenarios(load_scenarios(), args.scenario)]`.

`_run_batch`: gọi `run_one(..., source=..., skill=args.skill == "on")`.

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `uv run --extra dev pytest -q`
Expected: PASS toàn bộ (kể cả `tests/test_replay.py` — 3 kịch bản code replay `get_issue`/`resolve_bug` trên trạng thái `fix_code`).

- [ ] **Step 5: Smoke một lượt (có tốn model, ~2 phút)**

Chạy `--skill off` (skill chưa tồn tại; đường chép skill đã có test ở Task 3):

Run: `uv run --extra dev python -m evals.run --agent claude --model opus --scenario fix_code_on_main --runs 1 --label smoke-code`
Expected: in `[fix_code_on_main #1] PASS` hoặc `FAIL <lý do>` (không `ISOLATION FAILED`, không traceback). Mở `evals/results/*-smoke-code/claude-opus.jsonl`: `deniedTools` không chứa `Edit`/`Write`; `code` có đủ khoá. Nếu `deniedTools` chứa lệnh Bash cần thiết (ví dụ `ls`), ghi lại, không nới quyền trong task này.

- [ ] **Step 6: Commit**

```bash
git add backlog_tool/telemetry_grader.py evals/agents.py evals/run.py evals/scenarios.json tests/test_telemetry_grader.py tests/test_eval_run.py
git commit -m "Run code-fixing scenarios: git workspace, code tools, code checks, --skill"
```

---

### Task 6: RED — baseline không skill

**Files:**
- Create: `evals/results/<ngày>-skill-off/SUMMARY.md` (sinh tự động, thêm ghi chú)

- [ ] **Step 1: Chạy baseline (nền, ~15–25 phút)**

Run: `uv run --extra dev python -m evals.run --agent claude --model opus --scenario code --runs 3 --label skill-off --skill off`
Expected: 9 dòng kết quả, không `ISOLATION FAILED`.

- [ ] **Step 2: Ghi nhận hành vi**

Với từng lượt đọc `claude-opus.jsonl` (`code`, `mcpCalls`, `nonMcpCalls`, `deniedTools`, `finalAnswer`) và ghi vào mục "Ghi chú" của `SUMMARY.md`, mỗi kịch bản một đoạn: đã chạy test chưa, commit message, có push/push lên `main` không, resolve trước/sau push, có `commit`/`fix_description` không, câu biện minh nguyên văn khi vượt điểm dừng.

- [ ] **Step 3: Commit**

```bash
git add evals/results/*-skill-off/SUMMARY.md
git commit -m "Record the no-skill baseline for the code-fixing scenarios"
```

---

### Task 7: GREEN — viết skill và chạy có skill

**Files:**
- Create: `skills/fix-backlog-bug/SKILL.md`

- [ ] **Step 1: Viết skill**

Bắt đầu từ bản dưới; giữ mọi bước quy trình (đó là yêu cầu của spec), còn bảng "Stop, don't resolve" chỉ giữ các dòng ứng với lỗi thấy ở Task 6 và thêm câu biện minh nguyên văn đã ghi. Không tóm tắt quy trình trong `description`. Mục tiêu < 500 từ (`wc -w`).

```markdown
---
name: fix-backlog-bug
description: Use when the user asks to fix a Backlog bug given its issue key or link (e.g. "backlog fix OOP-123", "sửa bug OOP-123") and the fix should end with the bug resolved in Backlog.
---

# Fix a Backlog bug

Take one Backlog bug from report to resolved. The Backlog MCP reads and resolves the bug; this skill sets the order, the stops, and everything outside Backlog (code, tests, git).

## Steps

1. **Locate the repo.** In a git repo whose `.backlog-project.json` `project_key` equals the key prefix (OOP-123 → OOP): work here. Another project: stop and ask. Not in a repo: ask for the repo path.
2. **Check git.** `git status --porcelain` not empty → stop and ask; never mix the user's changes into the fix. Branch `main`/`master`, or no upstream (`git rev-parse --abbrev-ref @{u}` fails) → you may fix the code, but stop before committing and say why.
3. **Read the bug:** `get_issue(issue_key)`. Work from steps_to_reproduce, actual, expected. Attachments are listed, not fetched: if one looks essential, tell the user.
4. **Fix the cause** with the smallest change.
5. **Run the repo's tests.** Command from CLAUDE.md / AGENTS.md / README, else `package.json` `test`, `Makefile` `test`, `python -m pytest`, `go test ./...`. No test command → skip and say so in the report.
6. **Any failing test → stop.** No commit, no push, no resolve; report the failing tests.
7. **Commit only the fix:** `fix(OOP-123): <what changed, short>` (commitlint).
8. **Push** the current branch with `git push`; never `--force`. Rejected → stop, no resolve.
9. **Resolve:** `resolve_bug(issue_key, mode="apply", commit=<pushed short sha>, fix_description=<text after "fix(OOP-123): ">)`.
10. **Report** the fix, the test result, the commit, and resolve_bug's changes and warnings.

## Stop, don't resolve

| Thought | Reality |
|---|---|
| "The failing test is unrelated to my fix" | Any red test blocks the resolve: the tester gets a broken build. Report it. |
| "I'm on main, it's a one-line fix" | No commit on main/master. Stop and say so. |
| "The push failed, but the commit exists" | Resolve would send the tester to code that is not on the remote. |
```

- [ ] **Step 2: Chạy có skill (nền)**

Run: `uv run --extra dev python -m evals.run --agent claude --model opus --scenario code --runs 3 --label skill-on --skill on`
Expected: 3/3 mỗi kịch bản. Kiểm `nonMcpCalls` có lệnh test; `code.commitMessage` khớp mẫu.

- [ ] **Step 3: Commit**

```bash
git add skills/fix-backlog-bug/SKILL.md evals/results/*-skill-on/SUMMARY.md
git commit -m "Add the fix-backlog-bug skill: 9/9 on the code-fixing scenarios"
```

(Thay "9/9" bằng kết quả thật; nếu chưa đạt 3/3 mỗi kịch bản, sang Task 8 trước khi commit kết quả.)

---

### Task 8: REFACTOR — vá lỗ hổng, kiểm lại eval MCP, tài liệu

**Files:**
- Modify: `skills/fix-backlog-bug/SKILL.md`
- Modify: `docs/telemetry.md` (mục Eval)

- [ ] **Step 1: Vá** — mỗi lượt fail ở Task 7: ghi câu biện minh nguyên văn vào bảng "Stop, don't resolve" (hoặc sửa bước tương ứng nếu là lỗi dạng output), chạy lại đúng kịch bản đó `--runs 3 --skill on` cho tới khi 3/3.

- [ ] **Step 2: Eval MCP không đổi**

Run: `uv run --extra dev python -m evals.run --agent claude --model opus --scenario all --runs 3 --label mcp-after-skill`
Expected: 21/21 (kịch bản code không nằm trong `all`).

- [ ] **Step 3: Tài liệu** — thêm vào mục `## Eval` của `docs/telemetry.md`:

```markdown
- Kịch bản sửa code (trường `code`): `--scenario code` (không nằm trong `all`), chỉ `--agent claude`, chạy bằng `uv run --extra dev python -m evals.run …` (grader chạy test ẩn bằng pytest). Workspace là repo git tạm từ `evals/fixtures/<fixture>` (+ `<fixture>_variants/<variant>`) với remote bare tạm và upstream theo `branch`; marker và `.claude/` nằm trong `.git/info/exclude`. Agent được Read/Glob/Grep/Edit/Write và Bash `git`/`pytest`. `--skill on` chép `skills/fix-backlog-bug/` vào `.claude/skills/`. Grader thêm `code`: test ẩn, commit mới nhất khớp `commitPattern`, đã push, `resolve_bug` apply với tiền tố ≥7 của SHA đã push.
```

- [ ] **Step 4: Commit**

```bash
git add skills/fix-backlog-bug/SKILL.md docs/telemetry.md evals/results
git commit -m "Close the skill's loopholes and document the code-fixing eval"
git push origin main
```
