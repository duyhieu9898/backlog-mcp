# Plan B — Sửa MCP theo baseline và eval lại (P5–P6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (người dùng yêu cầu chạy inline, không subagent). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa Backlog MCP theo spec §9 và những gì baseline P4 chỉ ra (resolve một lần `mode="apply"`, text content là JSON đầy đủ, liệt kê tệp đính kèm, 12 tool, tên tham số chuẩn, lỗi tham số có gợi ý), rồi eval lại 10 lượt/kịch bản/model cho tới khi đạt ≥ 9/10 và 0 `arg_error`.

**Architecture:** Mọi thay đổi hành vi nằm ở ba chỗ: `backlog_mcp/server.py` (bề mặt tool, docstring, instructions, validate mã issue, định dạng response `resolve_bug`), `backlog_mcp/results.py` + `backlog_mcp/arg_errors.py` (text content, thông điệp lỗi tham số), `workflows/` (bỏ ràng buộc `fix_description`, attachments trong bug context). Test hợp đồng mới `tests/test_tool_contract.py` khoá bề mặt tool; `tests/test_replay.py` bỏ `xfail`. P6 dùng harness đã có (`evals/run.py`).

**Tech Stack:** Python ≥3.10, `mcp` FastMCP (stdio), pydantic, pytest. Không thêm dependency.

**Spec:** `docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md` (§9 = P5, §10 = điều kiện đóng). Đọc kèm `docs/superpowers/plans/2026-09-24-plan-b-handoff.md` (kết quả baseline) và `evals/results/2026-09-24-baseline*/SUMMARY.md`.

## Global Constraints

- Commit thẳng `main`, `git push origin main` sau mỗi task. Không branch, không PR.
- Mỗi commit kết thúc bằng dòng: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
- Không thêm dependency vào `pyproject.toml`.
- Không ghi API key, không ghi URL có query string vào log hay response.
- Repo public: chỉ commit `SUMMARY.md` của eval; `evals/results/**/*.jsonl`, `evals/cassettes/`, `tests/fixtures/local/` bị gitignore.
- MCP còn đúng 12 tool (D7): `get_issue`, `get_issues`, `create_issue`, `update_issue`, `get_my_open_bugs`, `get_bug_context`, `resolve_bug`, `create_ut_bug`, `get_bug_rules`, `get_bug_fields`, `get_my_work_overview`, `get_my_project_status`.
- `resolve_bug`: một lần `mode="apply"`, không bị chặn bởi warning, `fix_description`/`commit` không bắt buộc (D5, D6). `create_issue`, `update_issue`, `create_ut_bug` giữ preview → hỏi → apply; `mode` mặc định vẫn là `"preview"` ở cả 4 tool ghi.
- Text content = `json.dumps(structuredContent, separators=(",", ":"), ensure_ascii=False)` cho mọi kết quả thành công (§9.4).
- Log vẫn là schema `v = 3`; không đổi tên field log. Log cũ có `issue_ref` phải vẫn đọc được (`telemetry.py` giữ `issue_ref` trong danh sách key).
- Lệnh test: `uv run --extra dev pytest -q`. Lint: `uvx ruff check --select F backlog_mcp backlog_tool workflows evals`.
- Lệnh eval viết tường minh từng dòng (shell là zsh, `set -- $var` không tách từ).

## Review Focus

1. Model truyền mã issue chữ thường hoặc có khoảng trắng (`" oop-912762 "`) → được chuẩn hoá thành `OOP-912762` và chạy bình thường, không báo lỗi. (Task 3)
2. `resolve_bug` apply trên bug đã Resolved/Closed hoặc không gán cho mình → lỗi rõ ràng, không có PATCH nào gửi đi. (Task 5)
3. Response có chuỗi tiếng Việt, `date`/`datetime` hoặc giá trị không serialize được → text vẫn là JSON hợp lệ, giữ nguyên dấu tiếng Việt, `json.loads(text) == structuredContent` sau khi serialize. (Task 4)
4. Tham số sai không có tên nào gần giống (`{"foo": 1}`) hoặc thiếu tham số bắt buộc mà không có tham số lạ → thông điệp không có "did you mean", vẫn liệt kê `Valid parameters`. (Task 1)
5. Issue không có field `attachments` hoặc `attachments: null` → `get_bug_context` không có khoá `attachments`, không lỗi. (Task 6)

---

## File Structure

| File | Trạng thái | Trách nhiệm |
|---|---|---|
| `backlog_mcp/arg_errors.py` | sửa | thêm `format_arg_error(tool, details, valid)` dựng thông điệp §9.3 |
| `backlog_mcp/server.py` | sửa | 12 tool; `issue_key`; `_issue_key()` validate; docstring; `SERVER_INSTRUCTIONS`; response `resolve_bug`; bỏ prompt + `backlog://config` |
| `backlog_mcp/results.py` | sửa | text = JSON compact; list có `count`; bỏ `_to_markdown` |
| `workflows/resolve_bug.py` | sửa | bỏ bắt buộc `fix_description`; warning thông tin; apply trả cả kế hoạch; `public_changes()` |
| `workflows/resolve_policy.py` | sửa | help CLI `--fix-description` không còn "Required" |
| `workflows/bug_template.py` | sửa | `attachments` trong `bug_context` |
| `tests/test_tool_contract.py` | tạo | hợp đồng bề mặt tool (§9.2, §9.4) |
| `tests/test_mcp_server.py`, `tests/test_bug_workflow.py`, `tests/test_arg_errors.py`, `tests/test_bug_guidance.py` | sửa | theo hành vi mới |
| `tests/test_replay.py` | sửa | bỏ `NEEDS_PLAN_B` |
| `evals/run.py`, `tests/test_eval_run.py` | sửa | cột `ArgErr` trong `SUMMARY.md` (P6) |
| `docs/superpowers/specs/…design.md`, `docs/telemetry.md`, `README.md`, `ARCHITECTURE.md` | sửa | cập nhật theo hành vi mới |

---

## P5 — Sửa MCP

### Task 1: Thông điệp lỗi tham số có gợi ý (§9.3)

**Files:**
- Modify: `backlog_mcp/arg_errors.py`, `backlog_mcp/server.py:121-152`
- Test: `tests/test_arg_errors.py`, `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `format_arg_error(tool: str, details: dict, valid_params: list[str]) -> str` (details = kết quả `describe_validation_error`).

- [ ] **Step 1: Viết test hỏng**

`tests/test_arg_errors.py` (thêm):
```python
from backlog_mcp.arg_errors import format_arg_error


def test_format_arg_error_suggests_and_lists_valid():
    details = {"unknown": ["issueKey"], "missingRequired": ["issue_key"], "invalid": [], "suggested": {"issueKey": "issue_key"}}
    text = format_arg_error("resolve_bug", details, ["issue_key", "status", "mode"])
    assert text == ("Invalid arguments for resolve_bug: unknown 'issueKey' (did you mean 'issue_key'?); "
                    "missing required 'issue_key'. Valid parameters: issue_key, status, mode")


def test_format_arg_error_without_close_match_or_unknown():
    details = {"unknown": ["foo"], "missingRequired": [], "invalid": [{"name": "limit", "reason": "less_than_equal"}], "suggested": {}}
    text = format_arg_error("get_issues", details, ["limit"])
    assert "did you mean" not in text
    assert text == "Invalid arguments for get_issues: unknown 'foo'; invalid 'limit' (less_than_equal). Valid parameters: limit"
    missing_only = {"unknown": [], "missingRequired": ["issue_key"], "invalid": [], "suggested": {}}
    assert format_arg_error("get_bug_context", missing_only, ["issue_key"]) == (
        "Invalid arguments for get_bug_context: missing required 'issue_key'. Valid parameters: issue_key")
```

`tests/test_mcp_server.py` — thêm vào cuối `test_rejected_arguments_logged_with_suggestion`, đổi `pytest.raises(Exception)` thành bắt thông điệp:
```python
    with pytest.raises(Exception, match=r"unknown 'issueKey' \(did you mean 'issue_key'\?\)"):
        anyio.run(server.mcp.call_tool, "resolve_bug", {"issueKey": "OOP-1"})
```
(đặt `with` này thay cho `with` cũ ở đầu test; các assert log giữ nguyên).

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_arg_errors.py tests/test_mcp_server.py -q -k "format_arg_error or rejected_arguments"`
Expected: FAIL — `ImportError: cannot import name 'format_arg_error'`.

- [ ] **Step 3: Cài đặt**

`backlog_mcp/arg_errors.py` (thêm cuối file):
```python
def format_arg_error(tool, details, valid_params):
    parts = []
    for name in details.get("unknown") or []:
        hint = details.get("suggested", {}).get(name)
        parts.append(f"unknown '{name}'" + (f" (did you mean '{hint}'?)" if hint else ""))
    parts += [f"missing required '{name}'" for name in details.get("missingRequired") or []]
    parts += [f"invalid '{item['name']}' ({item['reason']})" for item in details.get("invalid") or []]
    return f"Invalid arguments for {tool}: {'; '.join(parts)}. Valid parameters: {', '.join(valid_params)}"
```

`backlog_mcp/server.py` — trong `call_tool_with_rejection_log`, thay nhánh `ValidationError` và `raise` cuối:
```python
        except ToolError as error:
            cause = error.__cause__
            status = "invalid_arguments" if isinstance(cause, ValidationError) else "rejected"
            start_call(name, arguments)
            if isinstance(cause, ValidationError):
                tool = manager.get_tool(name)
                valid = list((tool.parameters or {}).get("properties", {})) if tool else []
                details = describe_validation_error(cause, valid)
                record_arg_error(name, arguments, details)
                error = ToolError(format_arg_error(name, details, valid))
                error.__cause__ = cause
            _error_result(name, error, status=status)
            raise error
```
và import `from .arg_errors import describe_validation_error, format_arg_error`.

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `uv run --extra dev pytest tests/test_arg_errors.py tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit + push**

```bash
git add backlog_mcp/arg_errors.py backlog_mcp/server.py tests/test_arg_errors.py tests/test_mcp_server.py
git commit -m "Return argument errors with name suggestions and the valid parameter list"
git push origin main
```

### Task 2: Thu gọn MCP còn 12 tool (§9.1, D7)

**Files:**
- Modify: `backlog_mcp/server.py` (xoá `list_configured_projects`, `get_config`, `audit_config_workflows`, `inspect_project`, 3 `@mcp.prompt`, resource `backlog://config` + `config_resource`; giữ `redact_config` chỉ khi CLI còn dùng — kiểm tra `grep -rn redact_config backlog_tool`), bỏ import không dùng (`project_keys`, `load_project_catalog`, `audit_config`, `build_project_config`, `write_catalog`) sau khi Task 3 không cần chúng (Task 3 dùng lại `project_keys` — giữ import đó).
- Test: tạo `tests/test_tool_contract.py`; sửa `tests/test_mcp_server.py` (xoá `test_inspect_project_does_not_write_by_default`, `test_audit_config_workflows_live_mode_is_read_only`, `test_personal_prompts_use_minimal_domain_paths`, `test_config_resource_excludes_sensitive_keys`; trong `test_tool_schema_exposes_enums_and_use_when_descriptions` bỏ 3 dòng `audit_tool`; trong `test_resources_have_json_mime_type_and_issue_template` bỏ assert `backlog://config` và thêm assert nó không còn).

**Interfaces:**
- Produces: `tests/test_tool_contract.py` với fixture module-level `TOOLS = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}` mà Task 3, 4 thêm test vào.

- [ ] **Step 1: Viết test hỏng**

`tests/test_tool_contract.py`:
```python
"""Contract for the MCP tool surface the models see (spec §9.1, §9.2, §9.4)."""

import anyio

from backlog_mcp import server

EXPECTED_TOOLS = {
    "get_issue", "get_issues", "create_issue", "update_issue", "get_my_open_bugs", "get_bug_context",
    "resolve_bug", "create_ut_bug", "get_bug_rules", "get_bug_fields", "get_my_work_overview", "get_my_project_status",
}
TOOLS = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}


def test_exactly_twelve_tools():
    assert set(TOOLS) == EXPECTED_TOOLS


def test_no_prompts_and_only_issue_resource_template():
    assert anyio.run(server.mcp.list_prompts) == []
    assert anyio.run(server.mcp.list_resources) == []
    templates = anyio.run(server.mcp.list_resource_templates)
    assert [t.uriTemplate for t in templates] == ["backlog://issue/{issue_key}"]
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_tool_contract.py -q`
Expected: FAIL — thừa 4 tool, có 3 prompt và `backlog://config`.

- [ ] **Step 3: Xoá code trong `server.py`**

Xoá nguyên các hàm `list_configured_projects`, `get_config`, `audit_config_workflows`, `inspect_project`, `resolve_bug_prompt`, `create_ut_bug_prompt`, `project_status_prompt`, `config_resource` (cùng decorator). Xoá `redact_config` nếu `grep -rn "redact_config" backlog_tool tests` chỉ còn các test vừa xoá. CLI giữ `config list-projects|audit-workflows|show` và `project inspect` (đã có sẵn, không đổi).

Sửa các test trong `tests/test_mcp_server.py` như ở mục Files.

- [ ] **Step 4: Chạy toàn bộ test + lint**

Run: `uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows evals`
Expected: PASS (4 xfail replay còn nguyên), ruff sạch.

- [ ] **Step 5: Commit + push**

```bash
git add -A backlog_mcp tests
git commit -m "Keep 12 MCP tools: admin tools, prompts and the config resource move to the CLI only"
git push origin main
```

### Task 3: Tên tham số `issue_key`, validate mã issue, mô tả tool (§9.2)

**Files:**
- Modify: `backlog_mcp/server.py` (`get_issue`, `update_issue`, mọi `Field(description=...)` của tham số mã issue, docstring `get_bug_context`, `get_bug_rules`, `get_bug_fields`)
- Test: `tests/test_tool_contract.py`, `tests/test_mcp_server.py:178-221` (đổi assert `issue_ref` → `issue_key`, bỏ assert `snake_case` trong mô tả)

**Interfaces:**
- Produces: `_issue_key(value: str, allow_numeric: bool = False) -> str` trong `server.py` — chuẩn hoá `strip().upper()`, kiểm tra `^[A-Z][A-Z0-9_]*-\d+$` (hoặc toàn số khi `allow_numeric`), kiểm tra tiền tố nằm trong `project_keys(get_config_instance())`; sai → `ValueError`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/test_tool_contract.py`:
```python
import re
import typing
from unittest import mock

import pytest

ISSUE_KEY_PARAMS = {"issue_key", "parent_key"}


def _params(tool):
    return tool.inputSchema.get("properties", {})


def test_parameters_are_snake_case_and_forbid_extras():
    for name, tool in TOOLS.items():
        assert tool.inputSchema.get("additionalProperties") is False, name
        for param in _params(tool):
            assert re.fullmatch(r"[a-z][a-z0-9_]*", param), (name, param)


def test_issue_parameters_use_canonical_names_with_example():
    for name, tool in TOOLS.items():
        params = _params(tool)
        assert not {"issue_ref", "issue_id", "issueKey"} & set(params), name
        for param in ISSUE_KEY_PARAMS & set(params):
            assert "OOP-123" in params[param]["description"], (name, param)
    assert "issue_key" in _params(TOOLS["get_issue"]) and "issue_key" in _params(TOOLS["update_issue"])


def test_fixed_value_parameters_are_enums():
    for name, tool in TOOLS.items():
        for param in ("mode", "order", "view"):
            if param in _params(tool):
                schema = _params(tool)[param]
                options = schema.get("enum") or [e for s in schema.get("anyOf", []) for e in s.get("enum", [])]
                assert options, (name, param)


def test_every_description_says_use_when():
    for name, tool in TOOLS.items():
        assert "Use when" in tool.description, name


@pytest.mark.parametrize("raw, expected", [(" oop-912762 ", "OOP-912762"), ("OOP-1", "OOP-1")])
def test_issue_key_is_normalized(raw, expected):
    with mock.patch.object(server, "get_config_instance", return_value={"projects": {"OOP": {}}}), \
         mock.patch.object(server, "project_keys", return_value=["OOP", "AQM"]):
        assert server._issue_key(raw) == expected


def test_issue_key_rejects_bad_format_and_unknown_project():
    with mock.patch.object(server, "get_config_instance", return_value={}), \
         mock.patch.object(server, "project_keys", return_value=["OOP", "AQM"]):
        with pytest.raises(ValueError, match="OOP-123"):
            server._issue_key("12345")
        assert server._issue_key("12345", allow_numeric=True) == "12345"
        with pytest.raises(ValueError, match="Configured projects: OOP, AQM"):
            server._issue_key("ZZZ-1")


def test_resolve_bug_rejects_unconfigured_prefix_without_backend_call():
    with mock.patch.object(server, "get_config_instance", return_value={}), \
         mock.patch.object(server, "project_keys", return_value=["OOP"]), \
         mock.patch.object(server.bug_workflow, "resolve_bug") as resolve:
        result = server.resolve_bug("ZZZ-1", mode="apply")
    assert result.isError and "Configured projects: OOP" in result.content[0].text
    resolve.assert_not_called()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_tool_contract.py -q`
Expected: FAIL — `issue_ref` còn tồn tại, thiếu `_issue_key`, mô tả thiếu `OOP-123`/"Use when".

- [ ] **Step 3: Cài đặt**

Trong `server.py` (sau `_workspace_path`):
```python
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


def _issue_key(value: str, allow_numeric: bool = False) -> str:
    """Normalize and validate an issue key before any Backlog call."""
    key = str(value or "").strip().upper()
    if allow_numeric and key.isdigit():
        return key
    if not ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue key '{value}'. Expected a Backlog key such as 'OOP-123'.")
    configured = project_keys(get_config_instance())
    if key.split("-")[0] not in configured:
        raise ValueError(f"Project '{key.split('-')[0]}' is not configured. Configured projects: {', '.join(configured)}")
    return key
```
(thêm `import re`). Gọi ở đầu khối `try` của từng tool, trước mọi call Backlog:
- `get_issue`: `issue_key = _issue_key(issue_key, allow_numeric=True)`
- `update_issue`, `get_bug_context`, `resolve_bug`: `issue_key = _issue_key(issue_key)`
- `create_ut_bug`: `parent_key = _issue_key(parent_key)`
- `create_issue`: `parent_key = _issue_key(parent_key) if parent_key else ""`
- `get_bug_rules`, `get_bug_fields`: `issue_key = _issue_key(issue_key) if issue_key else ""` (trước `_support_project_key`).

`project=` trong `_error_result` của các tool này tiếp tục dùng `project_key_from_issue_id(<giá trị gốc>)`.

Đổi tên tham số: `get_issue(issue_key: ...)`, `update_issue(issue_key: ...)` (truyền `issue_service.update_issue(config, issue_id=issue_key, ...)`, `issue_service.get_issue(config, issue_key)`).

Mô tả tham số (thay đúng văn bản):
- `get_issue.issue_key`: `"Backlog issue key such as 'OOP-123', or a numeric issue ID."`
- `update_issue.issue_key`, `get_bug_context.issue_key`, `resolve_bug.issue_key`: `"Backlog issue key such as 'OOP-123'."`
- `get_bug_rules.issue_key`, `get_bug_fields.issue_key`: `"Bug issue key such as 'OOP-123' whose project rules/options to show. Preferred over project_key when working on a specific bug."`
- `create_issue.parent_key`: `"Parent issue key such as 'OOP-123'. Omit or pass an empty string for no parent."`
- `create_ut_bug.parent_key`: `"Parent issue key such as 'OOP-123' to attach the UT bug to."`

Docstring (dòng "Use when" mới, giữ các dòng khác):
- `get_bug_context`: thêm dòng thứ hai `Use when a Backlog bug key/link is supplied and the user wants to understand, investigate or fix it (it is the primary entry point).` thay cho câu "This is the primary entry point when …".
- `get_bug_rules`: `Use only when …` → `Use when the user asks for the rules or resolve_bug needs clarification; not a normal step before resolve_bug.`
- `get_bug_fields`: `Use when a field is ambiguous, missing, or explicitly requested; not a normal step before resolve_bug.`
- Tool khác đã có "Use when" (kiểm lại bằng test).

Sửa `tests/test_mcp_server.py` trong `test_tool_schema_exposes_enums_and_use_when_descriptions`: `issue_ref` → `issue_key` (cả `get_issue` và `update_issue`), xoá 2 assert `"snake_case" in ...description`. Test nào gọi `server.get_issue(...)`/`server.update_issue(...)` với tên `issue_ref=` thì đổi thành `issue_key=`; test gọi tool với mã `AQM-…`/`OOP-…` cần `project_keys` trả được tiền tố đó — nếu config test không có, patch `server.project_keys` trong test đó.

- [ ] **Step 4: Chạy test**

Run: `uv run --extra dev pytest -q`
Expected: PASS (4 xfail replay).

- [ ] **Step 5: Commit + push**

```bash
git add backlog_mcp/server.py tests
git commit -m "Name issue parameters issue_key everywhere and validate issue keys before calling Backlog"
git push origin main
```

### Task 4: Text content là JSON đầy đủ, danh sách có `count` (§9.4, baseline `open_bugs_empty`)

**Files:**
- Modify: `backlog_mcp/results.py`
- Test: `tests/test_tool_contract.py`, `tests/test_mcp_server.py` (xoá `test_to_markdown_formatting` và import `_to_markdown`; dòng 145 `"Retrieved 1 items via 'get_issues'."` → assert JSON)

**Interfaces:**
- Produces: `_text(structured: dict) -> str`; `_build_result` với data là list trả `data = {list_key: [...], "count": len}`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/test_tool_contract.py`:
```python
import json
from datetime import date

from backlog_mcp.results import _build_result


@pytest.mark.parametrize("data, kwargs", [
    ([], {"list_key": "bugs", "paginated": True, "limit": 50}),
    ([{"issueKey": "OOP-1", "summary": "Lỗi đăng nhập", "startDate": date(2026, 9, 24)}], {"list_key": "bugs", "paginated": True, "limit": 50}),
    ({"dryRun": True, "issue": "OOP-1", "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": ["w"]}, {}),
    ({}, {}),
])
def test_text_is_full_json_of_structured_content(data, kwargs):
    result = _build_result(data, "get_my_open_bugs", **kwargs)
    text = result.content[0].text
    assert json.loads(text) == json.loads(json.dumps(result.structuredContent, default=str))
    assert "(structured data)" not in text and "No data." not in text
    assert ", " not in text[:40]  # compact separators


def test_list_results_state_count():
    empty = _build_result([], "get_my_open_bugs", list_key="bugs", paginated=True, limit=50)
    assert empty.structuredContent["data"] == {"bugs": [], "count": 0}
    assert '"count":0' in empty.content[0].text


def test_vietnamese_text_is_not_escaped():
    result = _build_result({"summary": "Lỗi đăng nhập"}, "get_issue")
    assert "Lỗi đăng nhập" in result.content[0].text
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_tool_contract.py -q -k "json or count or vietnamese"`
Expected: FAIL — text đang là markdown.

- [ ] **Step 3: Cài đặt `results.py`**

Xoá `_to_markdown`. Thêm:
```python
import json


def _text(structured: Any) -> str:
    return json.dumps(structured, separators=(",", ":"), ensure_ascii=False, default=str)
```
Trong `_build_result`: tính `envelope_data` như cũ, nhưng với list:
```python
    result_data = {list_key or "items": data, "count": len(data)} if isinstance(data, list) else data
```
rồi **sau** khi dựng `envelope_data` (kể cả `pagination`), đặt `text = _text(envelope_data)` và `structuredContent=json.loads(text)` để structured và text luôn cùng một bản đã serialize (giá trị `date` thành chuỗi ở cả hai). `_resource_uris(data)` giữ nguyên. `_error_result` và `_partial_write_result` giữ text hiện tại (`Error: …` / `Partial write: …`).

Sửa `tests/test_mcp_server.py`: xoá `test_to_markdown_formatting` + import; dòng 145 thành `assert json.loads(result.content[0].text) == result.structuredContent`; test nào so `structuredContent["data"] == {"issues": [...]}` thêm `"count": n`.

- [ ] **Step 4: Chạy test**

Run: `uv run --extra dev pytest -q`
Expected: PASS (4 xfail replay).

- [ ] **Step 5: Commit + push**

```bash
git add backlog_mcp/results.py tests
git commit -m "Send the full structured result as compact JSON text and state list counts"
git push origin main
```

### Task 5: `resolve_bug` một lần `mode="apply"` (§9.5, D5, D6)

**Files:**
- Modify: `workflows/resolve_bug.py`, `workflows/resolve_policy.py:19`, `backlog_mcp/server.py` (`resolve_bug`)
- Test: `tests/test_bug_workflow.py`, `tests/test_mcp_server.py`, `tests/test_replay.py`

**Interfaces:**
- Consumes: `_issue_key` (Task 3), `_build_result` (Task 4).
- Produces: `bug_workflow.resolve_bug(...)` apply trả `{"dryRun": False, **built, "updated": <issue sau PATCH>}` (preview như cũ: `{"dryRun": True, **built}`); `bug_workflow.public_changes(changes) -> list[{"field","from","to"}]`.

- [ ] **Step 1: Viết test hỏng**

`tests/test_bug_workflow.py` — thay `test_resolve_apply_requires_fix_description` bằng:
```python
    def test_resolve_apply_without_fix_description_uses_summary(self):
        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        payload = self.client.update_issue.call_args.args[1]
        corrective = [v for k, v in payload.items() if isinstance(v, str) and v.startswith("fixed ")]
        self.assertTrue(corrective)
        self.assertEqual("Resolved", result["updated"]["status"]["name"])
        self.assertTrue(any("fix_description not given" in w for w in result["warnings"]))
        self.assertFalse(any("requires fix_description" in w for w in result["warnings"]))

    def test_resolve_apply_on_excluded_status_sends_no_patch(self):
        self.client.get_issue.return_value = {**BUG_ISSUE, "status": {"name": "Closed"}}
        with self.assertRaisesRegex(ValueError, "excluded status"):
            bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        self.client.update_issue.assert_not_called()

    def test_public_changes_shape(self):
        changes = [
            {"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"},
            {"field": "Assignee", "key": "assigneeId", "from": {"id": 1, "name": "Dev"}, "value": {"id": 2, "name": "QC"}, "source": "createdUser"},
            {"field": "Start Date", "key": "startDate", "value": "2026-06-02"},
        ]
        self.assertEqual([
            {"field": "Status", "from": "Open", "to": "Resolved"},
            {"field": "Assignee", "from": "Dev", "to": "QC"},
            {"field": "Start Date", "from": None, "to": "2026-06-02"},
        ], bug_workflow.public_changes(changes))
```
(Nếu fixture `BUG_ISSUE`/`self.client` trong file dùng tên khác, dùng đúng tên đang có ở đầu `tests/test_bug_workflow.py`; tiền tố Corrective Action lấy từ template workflow hiện có — kiểm bằng test `test_corrective_action_strips_summary_prefix_when_no_fix_description` đang có.) Sửa test `test_corrective_action_strips_summary_prefix_when_no_fix_description` (dòng ~403): assert warning chứa `"fix_description not given"`.

`tests/test_mcp_server.py` (thêm):
```python
def test_resolve_bug_apply_response_shape():
    built = {
        "dryRun": False, "issue": "OOP-1", "project": "OOP", "payload": {}, "context": {},
        "assignment": {}, "warnings": ["Detected Role is Developer, not Tester; confirm the reporter is the intended QC assignee."],
        "changes": [{"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"}],
        "updated": {"issueKey": "OOP-1", "status": {"name": "Resolved"}, "assignee": {"id": 2, "name": "QC"}},
    }
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value=built), \
         mock.patch("backlog_mcp.server.project_keys", return_value=["OOP"]), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}), \
         mock.patch("backlog_mcp.server.view_base_url", return_value="https://x.backlog.com"):
        result = server.resolve_bug("OOP-1", mode="apply")
    assert result.structuredContent["data"] == {
        "issue": "OOP-1", "status": "Resolved", "assignee": "QC", "url": "https://x.backlog.com/view/OOP-1",
        "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": built["warnings"],
    }
    assert "Tester" in result.content[0].text


def test_resolve_bug_preview_response_shape():
    built = {"dryRun": True, "issue": "OOP-1", "project": "OOP", "assignment": {"from": {}, "to": {}},
             "changes": [{"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"}], "warnings": []}
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value=built), \
         mock.patch("backlog_mcp.server.project_keys", return_value=["OOP"]), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}):
        result = server.resolve_bug("OOP-1")
    assert result.structuredContent["data"] == {
        "dryRun": True, "issue": "OOP-1", "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": [],
    }


def test_resolve_bug_description_says_apply_once():
    tools = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}
    description = tools["resolve_bug"].description
    assert 'only once, with mode="apply"' in description
    assert "Do not call get_bug_context, get_issue, get_bug_rules or get_bug_fields first." in description
    assert "Required in apply mode" not in tools["resolve_bug"].inputSchema["properties"]["fix_description"]["description"]
```
Trong `test_personal_routing_contract_is_explicit_and_domain_first`, đổi assert `"Do not pre-call get_bug_rules or get_bug_fields"` thành `"Do not call get_bug_context, get_issue, get_bug_rules or get_bug_fields first."`.

`tests/test_replay.py`: xoá 3 khoá `resolve_*` khỏi `NEEDS_PLAN_B`.

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_bug_workflow.py tests/test_mcp_server.py tests/test_replay.py -q`
Expected: FAIL — apply còn đòi `fix_description`, `public_changes` chưa có, response cũ.

- [ ] **Step 3: Cài đặt**

`workflows/resolve_bug.py`:
- Xoá khối `if not dry_run and not (kwargs.get("fix_description") ...): raise ValueError(...)` trong `resolve_bug`.
- Thay warning trong `build_resolution_plan`:
```python
    if not fix_description:
        warnings.append(
            "fix_description not given: Corrective Action uses the bug summary ('fixed <summary>')."
        )
```
- Cuối `resolve_bug`: `return {"dryRun": False, **built, "updated": updated}`.
- Thêm:
```python
def _change_value(value):
    return value.get("name") if isinstance(value, dict) else value


def public_changes(changes):
    """Changes as the model sees them: field, from, to (no Backlog wire keys or user IDs)."""
    return [
        {"field": change["field"], "from": _change_value(change.get("from")), "to": _change_value(change.get("value"))}
        for change in changes
    ]
```

`workflows/resolve_policy.py:19`: `"--fix-description": "Text for Corrective Action (fixed <text>). Optional; defaults to the bug summary."`

`backlog_mcp/server.py` — `resolve_bug`:
- `fix_description` description: `"What was changed, only if the user said it. Rendered into Corrective Action as 'fixed <text>' with casing preserved (write the object of 'fixed', e.g. 'OTP error message to include retry wait time'). Omit to use the bug summary."`
- `commit` description: `"Git commit hash/ref, only if the user gave it. Omit otherwise."`
- Docstring thay nguyên văn bằng khối trong spec §9.5 (8 dòng, bắt đầu "Resolve a Backlog bug the user says is fixed, using the configured workflow defaults.") và thêm dòng `Use when the user asks to resolve/close a Backlog bug or says it is already fixed.` sau dòng đầu (để qua test "Use when").
- Thân hàm: `issue_key = _issue_key(issue_key)` đầu `try`; sau khi gọi workflow:
```python
        changes = bug_workflow.public_changes(res.get("changes", []))
        if dry_run:
            data = {"dryRun": True, "issue": res.get("issue"), "changes": changes, "warnings": res.get("warnings", [])}
        else:
            updated = res.get("updated") or {}
            base_url = view_base_url(config)
            data = {
                "issue": res.get("issue"),
                "status": (updated.get("status") or {}).get("name"),
                "assignee": (updated.get("assignee") or {}).get("name"),
                "url": f"{base_url.rstrip('/')}/view/{res.get('issue')}" if base_url else None,
                "changes": changes,
                "warnings": res.get("warnings", []),
            }
```
- Sửa `test_resolve_bug_previews_by_default_and_applies_when_requested` cho mock trả dict có `changes`/`updated` và patch `project_keys`.

CLI `bug resolve --apply` giờ in cả kế hoạch và `updated` — chấp nhận (đầu ra JSON của CLI không có hợp đồng cố định); kiểm `tests/test_cli.py` nếu có assert trên kết quả apply và sửa theo.

- [ ] **Step 4: Chạy test**

Run: `uv run --extra dev pytest -q`
Expected: PASS; replay `resolve_fixed`, `resolve_multi`, `resolve_warning` PASS (không còn xfail); còn 1 xfail `fix_context_attachment`.

- [ ] **Step 5: Commit + push**

```bash
git add workflows backlog_mcp tests
git commit -m "Resolve bugs in one apply call without requiring fix_description, report changes and warnings"
git push origin main
```

### Task 6: `get_bug_context` liệt kê tệp đính kèm (§9.7)

**Files:**
- Modify: `workflows/bug_template.py`
- Test: `tests/test_bug_workflow.py` (thêm hàm test cấp module), `tests/test_replay.py`

**Interfaces:**
- Produces: `bug_context(issue)` thêm khoá `attachments: [{"id", "name", "size", "isImage"}]` chỉ khi issue có tệp.

- [ ] **Step 1: Viết test hỏng**

```python
from workflows.bug_template import bug_context


def test_bug_context_lists_attachments():
    issue = {"issueKey": "OOP-1", "attachments": [
        {"id": 7001, "name": "login-error.png", "size": 48213, "created": "x"},
        {"id": 7002, "name": "server.log", "size": 900},
    ]}
    assert bug_context(issue)["attachments"] == [
        {"id": 7001, "name": "login-error.png", "size": 48213, "isImage": True},
        {"id": 7002, "name": "server.log", "size": 900, "isImage": False},
    ]


def test_bug_context_without_attachments_has_no_key():
    for issue in ({"issueKey": "OOP-1"}, {"issueKey": "OOP-1", "attachments": None}, {"issueKey": "OOP-1", "attachments": []}):
        assert "attachments" not in bug_context(issue)
```
`tests/test_replay.py`: xoá `NEEDS_PLAN_B` và đoạn `if scenario_id in NEEDS_PLAN_B: …` (không còn phần tử nào), cùng tham số `request` nếu không dùng.

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests -q -k "attachments or replay"`
Expected: FAIL — chưa có `attachments`.

- [ ] **Step 3: Cài đặt**

`workflows/bug_template.py`:
```python
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")


def attachment_summary(attachments):
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "size": item.get("size"),
            "isImage": str(item.get("name") or "").lower().endswith(IMAGE_EXTENSIONS),
        }
        for item in attachments or []
    ]
```
Trong `bug_context`, dựng dict vào biến `context`, rồi:
```python
    attachments = attachment_summary(issue.get("attachments"))
    if attachments:
        context["attachments"] = attachments
    return context
```

- [ ] **Step 4: Chạy test**

Run: `uv run --extra dev pytest -q`
Expected: PASS, 0 xfail.

- [ ] **Step 5: Commit + push**

```bash
git add workflows/bug_template.py tests
git commit -m "List bug attachments in get_bug_context"
git push origin main
```

### Task 7: `SERVER_INSTRUCTIONS`, tài liệu, spec (§9.6; đóng P5)

**Files:**
- Modify: `backlog_mcp/server.py:82-112`, `tests/test_mcp_server.py:427-441`, `README.md`, `ARCHITECTURE.md`, `docs/telemetry.md`, `docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md`

- [ ] **Step 1: Viết test hỏng**

Thay thân `test_server_instructions_require_backlog_activation_and_minimal_bug_paths`:
```python
def test_server_instructions_require_backlog_activation_and_minimal_bug_paths():
    instructions = server.SERVER_INSTRUCTIONS
    assert "Activation:" in instructions and "without an activation signal" in instructions
    assert '-> resolve_bug directly with mode="apply" (one call)' in instructions
    assert "-> get_bug_context (it lists attachments" in instructions
    assert "resolve_bug: apply directly when the user asks to resolve; report warnings afterwards." in instructions
    assert "create_issue, update_issue, create_ut_bug: preview first, apply only after the user confirms." in instructions
    assert "preview -> apply" not in instructions
    assert "Project resolution:" in instructions and "Security:" in instructions
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `uv run --extra dev pytest tests/test_mcp_server.py -q -k server_instructions`
Expected: FAIL.

- [ ] **Step 3: Cài đặt**

`SERVER_INSTRUCTIONS` = khối Activation hiện có + khối sau (thay "Preferred tools", "Bug workflow", "Mutation safety") + Project resolution + Security hiện có:
```
Preferred tools:
- My open bugs -> get_my_open_bugs
- Resolve/close a bug, or the user says it is already fixed -> resolve_bug directly with mode="apply" (one call)
- Fix/investigate a bug that is not fixed yet -> get_bug_context (it lists attachments; tell the user when an attachment matters instead of fetching it)
- Personal status -> get_my_project_status
- Generic get/search/update tools are escape hatches only.

Mutation safety:
- resolve_bug: apply directly when the user asks to resolve; report warnings afterwards.
- create_issue, update_issue, create_ut_bug: preview first, apply only after the user confirms.
```

Tài liệu:
- Spec §8.3: bảng adapter `agy` bỏ `--sandbox`; thay đoạn "An toàn khi eval" bằng mô tả thật: `claude` dùng `--strict-mcp-config` + MCP config chỉ có `backlog` + `--disallowedTools …`; `agy` không `--sandbox`, runner tạm tắt MCP server global khác; env bỏ `BACKLOG_*`; fake backend; mã `OOP-9xxxxx`. §9.4 thêm: danh sách có `count`. Trạng thái spec → "Đã duyệt; P0–P5 xong".
- `README.md`, `ARCHITECTURE.md`: danh sách tool còn 12; 4 tool quản trị dùng qua CLI (`backlog config list-projects|audit-workflows|show`, `backlog project inspect`); `resolve_bug` một lần apply; bỏ nhắc MCP prompt và `backlog://config`. Tìm chỗ cần sửa: `grep -n "get_config\|audit_config_workflows\|inspect_project\|list_configured_projects\|prompt\|backlog://config\|issue_ref\|fix_description" README.md ARCHITECTURE.md docs/telemetry.md`.

- [ ] **Step 4: Chạy test + lint + replay**

Run: `uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows evals`
Expected: PASS toàn bộ, 0 xfail, ruff sạch.

- [ ] **Step 5: Commit + push (đóng P5)**

```bash
git add -A backlog_mcp tests README.md ARCHITECTURE.md docs
git commit -m "Route resolve to one apply call in server instructions and document the 12-tool surface"
git push origin main
```

---

## P6 — Eval lại

### Task 8: Cột `ArgErr` trong `SUMMARY.md`

**Files:**
- Modify: `evals/run.py` (`write_summary`)
- Test: `tests/test_eval_run.py`

- [ ] **Step 1: Viết test hỏng** — sửa `test_write_summary` và `test_write_summary_counts_env_errors`:
```python
    assert "| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |" in text
    assert "| open_bugs | 2/3 | 0 | 0 | 200 | 6500 |" in text
```
và `"| open_bugs | 1/2 | 1 | 0 | - | - |"`; thêm test:
```python
def test_write_summary_counts_runs_with_arg_errors(tmp_path):
    rows = [{"scenario": "resolve_fixed", "pass": False, "argErrors": [{"tool": "resolve_bug"}], "reasons": ["argument errors: x"]},
            {"scenario": "resolve_fixed", "pass": True, "argErrors": []}]
    (tmp_path / "claude-opus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    assert "| resolve_fixed | 1/2 | 0 | 1 | - | - |" in (tmp_path / "SUMMARY.md").read_text()
```

- [ ] **Step 2: Chạy, xác nhận FAIL**: `uv run --extra dev pytest tests/test_eval_run.py -q -k summary`

- [ ] **Step 3: Cài đặt** — trong `write_summary`: header `| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |`, separator 6 cột, `arg = sum(bool(row.get("argErrors")) for row in group)`, dòng `f"| {scenario} | {ok}/{len(group)} | {env} | {arg} | {tokens} | {wall} |"`.

- [ ] **Step 4: Chạy**: `uv run --extra dev pytest -q` → PASS.

- [ ] **Step 5: Commit + push**: `git commit -m "Count runs with argument errors in the eval summary"`.

### Task 9: Chạy ma trận P6, phân tích, lặp tới khi đạt (đóng P6)

Không có code mới trừ khi phân tích chỉ ra cần sửa. Mỗi lượt sửa MCP trong task này đi theo đúng vòng TDD như Task 1–7 (test hỏng → sửa → test xanh → commit + push), sau đó chạy lại **chỉ** kịch bản × model chưa đạt với nhãn mới (`p6-r2`, `p6-r3`, …).

- [ ] **Step 1: Phạm vi model** — người dùng quyết (2026-09-24): chỉ `claude opus`. Gemini (Flash, Pro) bị loại khỏi eval vì API Gemini không ổn định trong ngày; baseline Flash không chạy lại.

- [ ] **Step 2: Chạy ma trận (nền, tuần tự, từng lệnh một)**

```bash
uv run python -m evals.run --agent claude --model opus --scenario all --runs 10 --label p6 --timeout 300
```
Kết quả ghi dần vào `evals/results/<ngày>-p6/`; bị ngắt thì chạy lại riêng kịch bản thiếu với `--scenario <id> --runs <số còn thiếu>` (file jsonl được nối thêm).

- [ ] **Step 3: Phân tích** — với mỗi ô chưa đạt (pass < 9/10 hoặc `ArgErr` > 0, không tính lượt `EnvErr`): đọc `reasons`, `mcpCalls` (tool, arguments, status), `nonMcpCalls`, `schemaReads`, `finalAnswer`, `stderrTail` trong jsonl (log MCP của từng run nằm trong thư mục tạm đã xoá; jsonl là nguồn duy nhất). Lượt `EnvErr` > 1/10 ở một ô → chạy bù cho đủ 10 lượt không lỗi môi trường.

- [ ] **Step 4: Sửa + chạy lại** các ô chưa đạt theo vòng TDD ở trên; nếu một ô không thể đạt vì giới hạn model (không phải MCP), ghi ngoại lệ đề xuất (kịch bản, model, lý do, số liệu) và **hỏi người dùng chấp nhận bằng văn bản** (§10).

- [ ] **Step 5: Báo cáo** — thêm vào cuối `evals/results/<ngày>-p6/SUMMARY.md` mục "So sánh với baseline" (viết tay): bảng kịch bản × model với pass baseline → P6, MCP call trung vị, `estTokens` trung vị, thời gian trung vị; ghi nhận client nào đưa cả text lẫn structured vào context (§9.4, §14). Cập nhật `README.md` mục eval (kết quả P6 + lệnh chạy). Cập nhật handoff/memory: dự án đóng.

- [ ] **Step 6: Commit + push**

```bash
git add evals/results/*-p6*/SUMMARY.md README.md docs
git commit -m "Record P6 re-eval results against the baseline"
git push origin main
```

---

## Quyết định của người dùng khi duyệt plan (2026-09-24)

1. Không giảm payload `get_my_open_bugs` trong Plan B (giữ phạm vi spec §3); P6 báo cáo `estTokens` để quyết sau.
2. Chỉ eval Claude opus; Gemini Flash và Pro bị loại (API Gemini không ổn định ngày 2026-09-24). Ma trận P6 = 7 kịch bản × 10 lượt = 70 lượt. Baseline so sánh = `evals/results/2026-09-24-baseline/` (claude).
