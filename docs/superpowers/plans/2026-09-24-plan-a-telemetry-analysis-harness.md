# Plan A — Telemetry nền tảng, phân tích, harness eval (P0–P3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay cơ chế log cũ bằng bộ log chuẩn (calls/errors/sessions/details), thêm tầng phân tích (flow, rule, chấm kịch bản, field thiếu, ghép transcript Claude) và harness eval chạy `claude -p` / `agy -p` trên Backlog giả — để Plan B đo baseline, sửa MCP và eval lại.

**Architecture:** `backlog_tool/telemetry.py` giữ ngữ cảnh một tool call trong `ContextVar`, gom API call/mutation, ghi 1 dòng `calls.jsonl` + 1 dòng `details/<ngày>.jsonl` khi call kết thúc, lỗi vào `errors.jsonl`, mỗi process 1 dòng `sessions.jsonl`. Các module `telemetry_store` / `telemetry_rules` / `telemetry_grader` / `telemetry_missing` / `claude_transcripts` / `telemetry_report` chỉ đọc log. Eval bật chế độ giả bằng file `.backlog-eval.json` trong workspace; `evals/` chứa kịch bản, Backlog giả và runner.

**Tech Stack:** Python ≥3.10, `mcp` FastMCP (stdio) + `mcp.client.stdio` cho replay test, `requests`, `http.server` (Backlog giả), pytest. Không thêm dependency.

**Spec:** `docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md` (đọc kèm; §-số trong plan này trỏ tới spec).

## Global Constraints

- Commit thẳng `main`, `git push origin main` cuối mỗi phase (P0, P1, P2, P3). Không branch, không PR.
- Mỗi commit kết thúc bằng dòng: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
- Không thêm dependency vào `pyproject.toml`.
- Không ghi API key, không ghi URL có query string vào log.
- Ghi log không bao giờ làm hỏng tool call; lỗi ghi → `settings.report_log_failure(path, error)` (cảnh báo stderr một lần mỗi file).
- stdout của MCP server chỉ dành cho giao thức MCP.
- Schema log `v = 3`; tên field đúng như spec §5.
- Plan A **không đổi** hành vi tool MCP mà model thấy (tên tool, tham số, text/structured response) — trừ việc xoá resource `backlog://metrics` và `backlog://workflow-efficiency`. Thay đổi hành vi tool thuộc Plan B (P5).
- Lệnh test: `uv run --extra dev pytest -q`. Lint: `uvx ruff check --select F backlog_mcp backlog_tool workflows evals`.

## Review Focus

1. Thư mục log không ghi được (quyền, đĩa đầy) giữa một tool call → tool vẫn trả kết quả bình thường, stderr có đúng một cảnh báo mỗi file. (Task 2)
2. API call xảy ra ngoài một tool call (bootstrap, script) hoặc `finish_call` được gọi khi chưa `start_call` → không crash, không ghi dòng rác. (Task 2)
3. `result` chứa giá trị không serialize được (dataclass, `bytes`, `set`, `datetime`) → vẫn ghi được `details` (chuyển thành chuỗi). (Task 2)
4. Transcript Claude có prompt dạng list content, có `<system-reminder>`, `<command-name>`, tin nhắn `isMeta`, hoặc tool_result → `import-claude` chỉ lấy prompt thật do người dùng gõ. (Task 11)
5. `.backlog-eval.json` trỏ tới host không phải localhost, hoặc chỉ nằm ở thư mục cha → server từ chối chạy fake / không bật fake. (Task 14)

---

## File Structure

| File | Trạng thái | Trách nhiệm |
|---|---|---|
| `backlog_tool/telemetry.py` | viết lại | Ghi log: session, call context, API call, mutation, lỗi, arg_error, dọn `details/` cũ |
| `backlog_mcp/arg_errors.py` | mới | Phân tích `ValidationError` → `unknown/missingRequired/invalid/suggested` |
| `backlog_mcp/results.py` | sửa | Dựng response + gọi `finish_call` |
| `backlog_mcp/server.py` | sửa | `start_call` trong tool, wrapper ghi arg_error, `log_session_start`, bỏ 2 resource |
| `backlog_tool/client.py` | sửa | `record_api_call` thay cho `log_event`/`log_telemetry` |
| `backlog_tool/issue_service.py`, `workflows/ut_bug.py`, `workflows/resolve_bug.py` | sửa | `record_mutation` thay cho `log_event("dry_run")` |
| `backlog_tool/cli.py` | sửa | Trace CLI, bỏ `log_event`/`log_metric`/`journal`, nhóm lệnh `telemetry` |
| `backlog_tool/settings.py` | sửa | `LOG_DIR` từ env, bỏ API log cũ, `apply_eval_marker` |
| `backlog_tool/journal.py`, `backlog_tool/workflow_efficiency.py` | xoá | |
| `backlog_tool/telemetry_store.py` | mới | Đọc log, dựng `Call`/`Flow`, nhóm flow |
| `backlog_tool/telemetry_rules.py` | mới | Rule chung (tầng 2) |
| `backlog_tool/telemetry_grader.py` | mới | Nạp kịch bản, nhận diện prompt, chấm (tầng 3) |
| `backlog_tool/telemetry_missing.py` | mới | Phát hiện field thiếu |
| `backlog_tool/claude_transcripts.py` | mới | Đọc transcript Claude Code thành flow |
| `backlog_tool/telemetry_report.py` | mới | Dựng báo cáo |
| `evals/__init__.py`, `evals/scenarios.json` | mới | Kịch bản |
| `evals/fake_backlog.py` | mới | Backlog giả + fixture |
| `evals/agents.py` | mới | Lệnh chạy + parser stream-json cho `claude` và `agy` |
| `evals/run.py` | mới | Runner: workspace, fake, agent, chấm, lưu kết quả |
| `docs/telemetry.md` | mới | Schema log, cách đọc, công thức mẫu, eval |
| `tests/…` | sửa/mới | Theo từng task |

---

## Phase P0 — Dọn dẹp

### Task 1: Xoá import thừa và code chết

**Files:**
- Modify: `backlog_mcp/server.py` (import dòng 7, 15; dòng 35 `IssueView`)
- Modify: `backlog_mcp/results.py` (import `current_trace_id`)
- Modify: `backlog_tool/client.py` (import `current_trace_id`; xoá 6 method `get_priorities`…`get_custom_fields`)
- Modify: `backlog_tool/cli.py` (import `save_config`, `summarize_metrics`; docstring đầu file)
- Modify: `backlog_tool/settings.py` (dòng 10–12 alias `SKILL_DIR`)
- Modify: `tests/test_mcp_server.py` (test `test_to_markdown_formatting`)
- Modify: `docs/superpowers/plans/2026-09-23-telemetry-and-payload.md` (dòng đầu)

- [ ] **Step 1: Sửa test đang dùng `server._to_markdown`** — trong `tests/test_mcp_server.py`, thêm `from backlog_mcp.results import _to_markdown` ở đầu file và thay hai chỗ `server._to_markdown(` bằng `_to_markdown(`.

- [ ] **Step 2: Tự động xoá import thừa**

Run: `uvx ruff check --select F401 --fix backlog_mcp backlog_tool workflows`
Expected: `Found 8 errors (8 fixed, 0 remaining).`

- [ ] **Step 3: Xoá code chết bằng tay**
  - `backlog_mcp/server.py`: xoá dòng `IssueView = Literal["compact", "full"]`.
  - `backlog_tool/settings.py`: xoá dòng comment `# Keep the old name as an internal compatibility alias for existing callers.` và dòng `SKILL_DIR = MCP_ROOT`.
  - `backlog_tool/client.py`: xoá 6 method `get_priorities`, `get_project_statuses`, `get_project`, `get_issue_types`, `get_categories`, `get_custom_fields`.
  - `backlog_tool/cli.py` docstring đầu file: đổi `story / metrics.` thành `story / telemetry.` và dòng `- every run is measured into logs/metrics.log` thành `- every run is traced into logs/ (see docs/telemetry.md)`.
  - `docs/superpowers/plans/2026-09-23-telemetry-and-payload.md`: chèn dòng đầu tiên `> Superseded by docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md` và một dòng trống.

- [ ] **Step 4: Kiểm tra không còn tham chiếu**

Run: `grep -rn "SKILL_DIR\|IssueView\|get_priorities\|get_project_statuses\|get_issue_types\|get_categories\|get_custom_fields" backlog_mcp backlog_tool workflows tests`
Expected: không có kết quả (trừ `get_custom_fields` nếu xuất hiện trong chuỗi khác — đọc từng dòng; `inspect.py` phải không dùng các method đã xoá).

- [ ] **Step 5: Chạy test + lint**

Run: `uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows`
Expected: tất cả PASS; `All checks passed!`

- [ ] **Step 6: Commit + push (đóng P0)**

```bash
git add -A backlog_mcp backlog_tool tests docs/superpowers/plans/2026-09-23-telemetry-and-payload.md
git commit -m "Remove unused imports and dead code before telemetry rewrite

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

---

## Phase P1 — Log nền tảng

### Task 2: Module telemetry mới

**Files:**
- Rewrite: `backlog_tool/telemetry.py`
- Create: `backlog_mcp/arg_errors.py`
- Modify: `backlog_tool/settings.py` (`LOG_DIR` từ env)
- Rewrite: `tests/test_telemetry.py`
- Create: `tests/test_arg_errors.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces (dùng ở Task 3–18):
  - `telemetry.SCHEMA_VERSION = 3`, `telemetry.SESSION_ID: str`
  - `telemetry.log_paths() -> dict` với key `calls`, `errors`, `sessions`, `details_dir`
  - `telemetry.set_surface(surface: str) -> None`; `telemetry.set_eval_tags(run_id: str | None, scenario: str | None) -> None`
  - `telemetry.set_client_arguments(arguments) -> Token`, `telemetry.reset_client_arguments(token)`
  - `telemetry.start_call(tool: str, arguments: dict | None = None) -> str` (traceId)
  - `telemetry.current_trace_id() -> str | None`, `telemetry.current_tool() -> str | None`
  - `telemetry.record_api_call(method, path, status, ok, duration_ms, request_bytes, response_bytes, body) -> None`
  - `telemetry.record_mutation(**fields) -> None`
  - `telemetry.record_error(kind: str, message: str, **fields) -> None`
  - `telemetry.record_arg_error(tool: str, arguments: dict, details: dict) -> None`
  - `telemetry.finish_call(status: str, *, result=None, text=None, response_bytes=0, project_key=None, issue_key=None, mode=None, error=None) -> str | None`
  - `telemetry.plan_hash(issue: str | None, payload: dict) -> str`
  - `telemetry.log_session_start(*, backend: str = "real", workspace: str | None = None, tool_count: int | None = None) -> None`
  - `telemetry.client_metadata() -> {"name", "version"}`, `telemetry.serialized_bytes(value) -> int`
  - `arg_errors.describe_validation_error(error, valid_params: list[str]) -> {"unknown", "missingRequired", "invalid", "suggested"}`

- [ ] **Step 1: `LOG_DIR` từ env** — trong `backlog_tool/settings.py` đổi `LOG_DIR = os.path.join(MCP_ROOT, "logs")` thành:

```python
LOG_DIR = os.environ.get("BACKLOG_MCP_LOG_DIR") or os.path.join(MCP_ROOT, "logs")
```

- [ ] **Step 2: Viết test fail cho telemetry** — thay toàn bộ `tests/test_telemetry.py`:

```python
import json
import os
from dataclasses import dataclass
from datetime import date, timedelta

from backlog_tool import settings, telemetry


def read(kind):
    path = telemetry.log_paths()[kind]
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_details():
    folder = telemetry.log_paths()["details_dir"]
    rows = []
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            rows += [json.loads(line) for line in handle if line.strip()]
    return rows


def test_call_writes_index_and_detail_linked_by_trace_id():
    trace = telemetry.start_call("resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    telemetry.record_api_call("GET", "/issues/OOP-1", 200, True, 12.5, 10, 300, '{"id": 1}')
    telemetry.record_api_call("PATCH", "/issues/OOP-1", 200, True, 20.0, 50, 400, '{"id": 1}')
    telemetry.record_mutation(mode="apply", planHash="abc", changedFields=["statusId"], warnings=[])
    returned = telemetry.finish_call("ok", result={"ok": True}, text="done", response_bytes=900, project_key="OOP")

    [call] = read("calls")
    [detail] = read_details()
    assert returned == trace == call["traceId"] == detail["traceId"]
    assert call["v"] == 3 and call["sessionId"] == telemetry.SESSION_ID and call["surface"] == "mcp"
    assert call["tool"] == "resolve_bug" and call["argKeys"] == ["issue_key", "mode"]
    assert call["issueKey"] == "OOP-1" and call["projectKey"] == "OOP" and call["mode"] == "apply"
    assert call["apiCalls"] == 2 and call["apiMs"] == 32.5
    assert call["responseBytes"] == 900 and call["estTokens"] == 225 and call["flags"] == []
    assert detail["arguments"] == {"issue_key": "OOP-1", "mode": "apply"}
    assert detail["result"] == {"ok": True} and detail["text"] == "done"
    assert [a["method"] for a in detail["api"]] == ["GET", "PATCH"]
    assert "body" not in detail["api"][0]
    assert detail["api"][1]["body"] == '{"id": 1}'
    assert detail["mutation"]["planHash"] == "abc"
    assert telemetry.current_trace_id() is None
    assert read("errors") == []


def test_full_body_env_keeps_successful_get_body(monkeypatch):
    monkeypatch.setenv("BACKLOG_MCP_LOG_BODIES", "full")
    telemetry.start_call("get_issue", {"issue_ref": "OOP-1"})
    telemetry.record_api_call("GET", "/issues/OOP-1", 200, True, 1.0, 1, 2, "{}")
    telemetry.finish_call("ok", result={}, text="", response_bytes=10)
    assert read_details()[0]["api"][0]["body"] == "{}"


def test_api_error_goes_to_errors_with_truncated_body():
    telemetry.start_call("get_issue", {"issue_ref": "OOP-9"})
    telemetry.record_api_call("GET", "/issues/OOP-9", 404, False, 3.0, 1, 5000, "x" * 5000)
    telemetry.finish_call("error", text="Error: not found", response_bytes=20, error="not found")

    errors = read("errors")
    kinds = [e["kind"] for e in errors]
    assert kinds == ["api_error", "tool_error"]
    assert errors[0]["status"] == 404 and len(errors[0]["body"]) == 2048
    assert errors[0]["traceId"] == errors[1]["traceId"] == read("calls")[0]["traceId"]
    assert errors[1]["tool"] == "get_issue" and errors[1]["message"] == "not found"


def test_large_response_flag():
    telemetry.start_call("get_issues", {})
    telemetry.finish_call("ok", result={}, text="", response_bytes=9000)
    assert read("calls")[0]["flags"] == ["large_response"]


def test_client_arguments_override_handler_locals():
    token = telemetry.set_client_arguments({"issue_key": "OOP-1"})
    try:
        telemetry.start_call("resolve_bug", {"issue_key": "OOP-1", "status": "", "comment": ""})
        telemetry.finish_call("ok", result={}, text="", response_bytes=1)
    finally:
        telemetry.reset_client_arguments(token)
    assert read_details()[0]["arguments"] == {"issue_key": "OOP-1"}


def test_eval_tags_and_cli_surface_are_on_every_line():
    telemetry.set_surface("cli")
    telemetry.set_eval_tags("run-1", "resolve_fixed")
    try:
        telemetry.start_call("resolve_bug", {"issue_key": "OOP-1"})
        telemetry.finish_call("error", text="x", response_bytes=1, error="boom")
    finally:
        telemetry.set_surface("mcp")
        telemetry.set_eval_tags(None, None)
    for row in read("calls") + read("errors") + read_details():
        assert row["surface"] == "cli" and row["runId"] == "run-1" and row["scenario"] == "resolve_fixed"


def test_arg_error_record():
    telemetry.start_call("resolve_bug", {"issueKey": "OOP-1"})
    telemetry.record_arg_error(
        "resolve_bug",
        {"issueKey": "OOP-1"},
        {"unknown": ["issueKey"], "missingRequired": ["issue_key"], "invalid": [], "suggested": {"issueKey": "issue_key"}},
    )
    telemetry.finish_call("invalid_arguments", text="Error", response_bytes=5, error="bad args")
    [error] = read("errors")
    assert error["kind"] == "arg_error" and error["sent"] == ["issueKey"]
    assert error["suggested"] == {"issueKey": "issue_key"}
    assert read("calls")[0]["status"] == "invalid_arguments"


def test_session_start_and_old_detail_purge():
    folder = telemetry.log_paths()["details_dir"]
    os.makedirs(folder, exist_ok=True)
    old = (date.today() - timedelta(days=31)).isoformat()
    recent = (date.today() - timedelta(days=5)).isoformat()
    for day in (old, recent):
        with open(os.path.join(folder, f"{day}.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("{}\n")

    telemetry.log_session_start(backend="fake", workspace="/tmp/ws", tool_count=16)

    [session] = read("sessions")
    assert session["event"] == "session_start" and session["pid"] == os.getpid()
    assert session["backend"] == "fake" and session["toolCount"] == 16 and "gitSha" in session
    assert sorted(os.listdir(folder)) == [f"{recent}.jsonl"]


def test_logging_failure_never_breaks_and_warns_once(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "LOG_DIR", str(blocker))
    monkeypatch.setattr(settings, "_reported_log_failures", set())
    for _ in range(2):
        telemetry.start_call("get_issue", {})
        assert telemetry.finish_call("ok", result={}, text="", response_bytes=1)
    err = capsys.readouterr().err
    assert err.count("calls.jsonl") == 1


def test_no_active_call_is_harmless():
    telemetry.record_api_call("GET", "/projects/OOP", 200, True, 1.0, 1, 1, "{}")
    telemetry.record_mutation(mode="preview")
    assert telemetry.finish_call("ok") is None
    assert read("calls") == []


@dataclass
class Thing:
    name: str


def test_unserializable_result_is_stringified():
    telemetry.start_call("get_issue", {})
    telemetry.finish_call("ok", result={"thing": Thing("a"), "raw": b"\x00", "tags": {"x"}}, text="", response_bytes=1)
    detail = read_details()[0]
    assert detail["result"]["thing"] == "Thing(name='a')"
    assert detail["result"]["tags"] == ["x"]


def test_plan_hash_is_order_independent_and_payload_sensitive():
    a = telemetry.plan_hash("OOP-1", {"statusId": 3, "comment": "x"})
    b = telemetry.plan_hash("OOP-1", {"comment": "x", "statusId": 3})
    c = telemetry.plan_hash("OOP-1", {"comment": "y", "statusId": 3})
    assert a == b != c and len(a) == 16
```

- [ ] **Step 3: Viết test fail cho arg_errors** — `tests/test_arg_errors.py`:

```python
from pydantic import BaseModel, ConfigDict, ValidationError

from backlog_mcp.arg_errors import describe_validation_error


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_key: str
    limit: int = 10


def error_for(payload):
    try:
        Args(**payload)
    except ValidationError as error:
        return error
    raise AssertionError("expected ValidationError")


def test_unknown_missing_invalid_and_suggestions():
    details = describe_validation_error(
        error_for({"issueKey": "OOP-1", "limt": "x"}),
        ["issue_key", "limit"],
    )
    assert details["unknown"] == ["issueKey", "limt"]
    assert details["missingRequired"] == ["issue_key"]
    assert details["suggested"] == {"issueKey": "issue_key", "limt": "limit"}
    assert details["invalid"] == []


def test_invalid_type_is_reported():
    details = describe_validation_error(error_for({"issue_key": "OOP-1", "limit": "abc"}), ["issue_key", "limit"])
    assert details["invalid"] == [{"name": "limit", "reason": "int_parsing"}]
    assert details["unknown"] == [] and details["suggested"] == {}


def test_no_suggestion_for_unrelated_name():
    details = describe_validation_error(error_for({"issue_key": "OOP-1", "zzzz": 1}), ["issue_key", "limit"])
    assert details["suggested"] == {}
```

- [ ] **Step 4: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_telemetry.py tests/test_arg_errors.py -q`
Expected: FAIL (`AttributeError: module 'backlog_tool.telemetry' has no attribute 'log_paths'`, `ModuleNotFoundError: backlog_mcp.arg_errors`).

- [ ] **Step 5: Viết `backlog_mcp/arg_errors.py`**

```python
"""Turn FastMCP/pydantic argument validation errors into loggable, model-friendly details."""

import difflib


def _normalize(name):
    return str(name).replace("_", "").replace("-", "").lower()


def _suggest(unknown, valid_params):
    by_norm = {_normalize(name): name for name in valid_params}
    suggestions = {}
    for name in unknown:
        norm = _normalize(name)
        if norm in by_norm:
            suggestions[name] = by_norm[norm]
            continue
        match = difflib.get_close_matches(norm, list(by_norm), n=1, cutoff=0.6)
        if match:
            suggestions[name] = by_norm[match[0]]
    return suggestions


def describe_validation_error(error, valid_params):
    unknown, missing, invalid = [], [], []
    for item in error.errors():
        name = str(item["loc"][0]) if item.get("loc") else ""
        kind = item.get("type", "")
        if kind == "extra_forbidden":
            unknown.append(name)
        elif kind == "missing":
            missing.append(name)
        else:
            invalid.append({"name": name, "reason": kind})
    return {
        "unknown": unknown,
        "missingRequired": missing,
        "invalid": invalid,
        "suggested": _suggest(unknown, valid_params),
    }
```

- [ ] **Step 6: Viết lại `backlog_tool/telemetry.py`**

```python
"""Structured local telemetry for the Backlog MCP server and CLI.

Layout (see docs/telemetry.md): calls.jsonl (index, one line per tool call),
errors.jsonl, sessions.jsonl, details/<YYYY-MM-DD>.jsonl (arguments, result,
API calls, mutation), all linked by traceId.
"""

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import settings

SCHEMA_VERSION = 3
SESSION_ID = uuid.uuid4().hex
LARGE_RESPONSE_BYTES = 8192
ERROR_BODY_LIMIT = 2048
DETAILS_RETENTION_DAYS = 30
INDEX_MAX_BYTES = 20 * 1024 * 1024
INDEX_BACKUPS = 5
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


@dataclass
class _Call:
    trace_id: str
    tool: str
    arguments: dict
    started: float
    api: list = field(default_factory=list)
    mutation: dict | None = None


_call: ContextVar[_Call | None] = ContextVar("backlog_telemetry_call", default=None)
_client_arguments: ContextVar[dict | None] = ContextVar("backlog_telemetry_client_arguments", default=None)
_surface: ContextVar[str] = ContextVar("backlog_telemetry_surface", default="mcp")
_eval_tags: dict[str, str] = {}


def log_paths():
    log_dir = settings.LOG_DIR
    return {
        "calls": os.path.join(log_dir, "calls.jsonl"),
        "errors": os.path.join(log_dir, "errors.jsonl"),
        "sessions": os.path.join(log_dir, "sessions.jsonl"),
        "details_dir": os.path.join(log_dir, "details"),
    }


def set_surface(surface):
    _surface.set(surface)


def set_eval_tags(run_id, scenario):
    _eval_tags.clear()
    if run_id:
        _eval_tags["runId"] = run_id
    if scenario:
        _eval_tags["scenario"] = scenario


def set_client_arguments(arguments):
    """Remember the arguments exactly as the MCP client sent them."""
    return _client_arguments.set(dict(arguments or {}))


def reset_client_arguments(token):
    _client_arguments.reset(token)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _jsonable(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [_jsonable(v) for v in items]
    return str(value)


def serialized_bytes(value):
    return len(json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _mcp_client_info():
    try:
        from mcp.server.lowlevel.server import request_ctx

        return getattr(request_ctx.get().session.client_params, "clientInfo", None)
    except Exception:
        return None


def client_metadata():
    info = _mcp_client_info()
    return {
        "name": os.environ.get("BACKLOG_MCP_CLIENT") or getattr(info, "name", None) or "unknown",
        "version": os.environ.get("BACKLOG_MCP_CLIENT_VERSION") or getattr(info, "version", None),
    }


def _common():
    return {
        "v": SCHEMA_VERSION,
        "ts": _now(),
        "sessionId": SESSION_ID,
        "surface": _surface.get(),
        "client": client_metadata(),
        **_eval_tags,
    }


def _append(path, record, *, rotate=True):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if rotate:
            settings.rotate_file_if_needed(path, max_bytes=INDEX_MAX_BYTES, backup_count=INDEX_BACKUPS)
        line = json.dumps({k: v for k, v in record.items() if v is not None}, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as error:
        settings.report_log_failure(path, error)


def _issue_from(arguments):
    for key in ("issue_key", "issue_ref", "issue_id", "parent_key"):
        value = arguments.get(key)
        if isinstance(value, str) and ISSUE_KEY_RE.match(value):
            return value
    return None


def start_call(tool, arguments=None):
    client_arguments = _client_arguments.get()
    source = client_arguments if client_arguments is not None else (arguments or {})
    args = {k: _jsonable(v) for k, v in source.items() if k not in {"started", "trace_id"}}
    call = _Call(uuid.uuid4().hex, tool, args, time.monotonic())
    _call.set(call)
    return call.trace_id


def current_trace_id():
    call = _call.get()
    return call.trace_id if call else None


def current_tool():
    call = _call.get()
    return call.tool if call else None


def record_api_call(method, path, status, ok, duration_ms, request_bytes, response_bytes, body):
    keep_body = os.environ.get("BACKLOG_MCP_LOG_BODIES") == "full" or not ok or method != "GET"
    entry = {
        "method": method,
        "path": path,
        "status": status,
        "durationMs": round(duration_ms, 1),
        "requestBytes": request_bytes,
        "responseBytes": response_bytes,
    }
    if keep_body:
        entry["body"] = body
    call = _call.get()
    if call is not None:
        call.api.append(entry)
    if not ok:
        record_error(
            "api_error",
            f"{method} {path} -> {status}",
            method=method,
            path=path,
            status=status,
            body=(body or "")[:ERROR_BODY_LIMIT],
        )


def record_mutation(**fields):
    call = _call.get()
    if call is not None:
        call.mutation = {k: _jsonable(v) for k, v in fields.items() if v is not None}


def record_error(kind, message, **fields):
    call = _call.get()
    record = {
        **_common(),
        "traceId": call.trace_id if call else None,
        "kind": kind,
        "tool": fields.pop("tool", None) or (call.tool if call else None),
        "message": message,
        **{k: _jsonable(v) for k, v in fields.items()},
    }
    _append(log_paths()["errors"], record)


def record_arg_error(tool, arguments, details):
    record_error(
        "arg_error",
        "invalid tool arguments",
        tool=tool,
        sent=sorted((arguments or {}).keys()),
        unknown=details.get("unknown", []),
        missingRequired=details.get("missingRequired", []),
        invalid=details.get("invalid", []),
        suggested=details.get("suggested", {}),
    )


def plan_hash(issue, payload):
    canonical = json.dumps(
        {"issue": issue, "payload": _jsonable(payload)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def finish_call(status, *, result=None, text=None, response_bytes=0, project_key=None, issue_key=None, mode=None, error=None):
    call = _call.get()
    if call is None:
        return None
    try:
        if status == "error":
            record_error("tool_error", error or "")
        elif status == "partial_write":
            record_error("partial_write", error or "")
        paths = log_paths()
        issue = issue_key or _issue_from(call.arguments)
        project = project_key or (issue.rsplit("-", 1)[0] if issue else None) or call.arguments.get("project_key") or None
        _append(paths["calls"], {
            **_common(),
            "traceId": call.trace_id,
            "tool": call.tool,
            "argKeys": sorted(call.arguments),
            "issueKey": issue,
            "projectKey": project,
            "mode": mode or call.arguments.get("mode"),
            "status": status,
            "durationMs": round((time.monotonic() - call.started) * 1000, 1),
            "apiCalls": len(call.api),
            "apiMs": round(sum(a["durationMs"] for a in call.api), 1),
            "responseBytes": response_bytes,
            "estTokens": round(response_bytes / 4),
            "flags": ["large_response"] if response_bytes > LARGE_RESPONSE_BYTES else [],
        })
        detail_path = os.path.join(paths["details_dir"], f"{date.today().isoformat()}.jsonl")
        _append(detail_path, {
            **_common(),
            "traceId": call.trace_id,
            "tool": call.tool,
            "arguments": call.arguments,
            "result": _jsonable(result),
            "text": text,
            "api": call.api,
            "mutation": call.mutation,
        }, rotate=False)
        return call.trace_id
    finally:
        _call.set(None)


def _git(*args):
    return subprocess.run(
        ["git", "-C", settings.MCP_ROOT, *args],
        capture_output=True, text=True, timeout=2,
    ).stdout.strip()


def server_version():
    try:
        git_sha = _git("rev-parse", "--short", "HEAD") or None
        dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    except Exception:
        git_sha, dirty = None, None
    try:
        version = importlib.metadata.version("hieund-backlog-mcp")
    except Exception:
        version = None
    return {"version": version, "gitSha": git_sha, "dirty": dirty}


def _purge_old_details():
    folder = log_paths()["details_dir"]
    cutoff = (date.today() - timedelta(days=DETAILS_RETENTION_DAYS)).isoformat()
    try:
        for name in os.listdir(folder):
            if name.endswith(".jsonl") and name[:10] < cutoff:
                os.remove(os.path.join(folder, name))
    except FileNotFoundError:
        return
    except Exception as error:
        settings.report_log_failure(folder, error)


def log_session_start(*, backend="real", workspace=None, tool_count=None):
    version = server_version()
    _append(log_paths()["sessions"], {
        **_common(),
        "event": "session_start",
        "pid": os.getpid(),
        "version": version["version"],
        "gitSha": version["gitSha"],
        "dirty": version["dirty"],
        "toolCount": tool_count,
        "backend": backend,
        "workspace": workspace,
    })
    _purge_old_details()
```

- [ ] **Step 7: Cập nhật `tests/conftest.py`** — thay thân fixture `isolated_log_paths` (giữ docstring) bằng:

```python
    if request.node.get_closest_marker("real_log_paths"):
        yield
        return
    from backlog_tool import telemetry

    monkeypatch.setattr(settings, "LOG_DIR", str(tmp_path / "logs"))
    # Transitional until Task 5 removes the legacy sinks: keep them out of the real logs/.
    for name, filename in (("LOG_PATH", "backlog.log"), ("METRICS_PATH", "metrics.log"), ("TELEMETRY_PATH", "telemetry.jsonl")):
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, str(tmp_path / "logs" / filename))
    if journal is not None:
        monkeypatch.setattr(journal, "SESSIONS_DIR", str(tmp_path / "logs" / "sessions"))
    telemetry.set_eval_tags(None, None)
    telemetry.set_surface("mcp")
    yield
    telemetry.set_eval_tags(None, None)
```

và đổi import đầu file thành:

```python
from backlog_tool import settings

try:  # removed in Task 5
    from backlog_tool import journal
except ImportError:
    journal = None
```

- [ ] **Step 8: Chạy test mới**

Run: `uv run --extra dev pytest tests/test_telemetry.py tests/test_arg_errors.py -q`
Expected: PASS. (Các test khác có thể fail vì module cũ bị thay — xử lý ở Task 3–5; không commit ở trạng thái đó.)

### Task 3: Nối MCP server và results vào telemetry mới

**Files:**
- Modify: `backlog_mcp/results.py`
- Modify: `backlog_mcp/server.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: Task 2 (`start_call`, `finish_call`, `current_trace_id`, `record_arg_error`, `log_session_start`, `set_client_arguments`, `reset_client_arguments`, `serialized_bytes`), `arg_errors.describe_validation_error`.
- Produces: `_build_result(data, tool, list_key=None, limit=0, offset=0, paginated=False, dry_run=None, project=None)`, `_error_result(tool, error, dry_run=None, project=None, status="error")`, `_partial_write_result(tool, message, data, project=None)` — **bỏ tham số `started`**.

- [ ] **Step 1: Viết test fail** — trong `tests/test_mcp_server.py`:
  - Xoá các test: `test_tool_execution_logs_metrics_on_success_and_error`, `test_result_metrics_include_structured_and_total_response_bytes`, `test_error_metrics_count_error_response_bytes`, `test_issue_scoped_tools_record_project_from_issue_key`, `test_workflow_efficiency_resource_serializes_analyzer`, `test_rejected_tool_arguments_are_recorded_in_metrics_and_telemetry`, `test_tests_never_write_workstation_logs`, và test cuối file `test_tool_start_omits_defaulted_mutation_arguments`.
  - Trong test resource (dòng ~256–262) xoá 4 dòng assert về `backlog://workflow-efficiency`.
  - Thêm vào cuối file:

```python
from backlog_tool import telemetry


def _rows(kind):
    path = telemetry.log_paths()[kind]
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _details():
    folder = telemetry.log_paths()["details_dir"]
    rows = []
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            rows += [json.loads(line) for line in handle if line.strip()]
    return rows


def test_tool_success_and_error_are_logged_with_project_from_issue_key():
    with mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", return_value={"issueKey": "OOP-1"}):
        ok = server.get_bug_context("OOP-1")
    with mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", side_effect=ValueError("Boom")):
        bad = server.get_bug_context("OOP-1")

    first, second = _rows("calls")
    assert (first["tool"], first["status"], first["projectKey"]) == ("get_bug_context", "ok", "OOP")
    assert (second["status"], second["projectKey"]) == ("error", "OOP")
    assert ok.meta["traceId"] == first["traceId"] and bad.meta["traceId"] == second["traceId"]
    assert _rows("errors")[0]["message"] == "Boom"
    assert _details()[0]["result"] == ok.structuredContent
    assert _details()[0]["text"] == ok.content[0].text


def test_response_bytes_count_full_serialized_result():
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value={"issueKey": "OOP-1", "description": "x" * 2000}):
        server.get_issue("OOP-1", view="full")
    call = _rows("calls")[0]
    assert call["responseBytes"] > 2000 and call["estTokens"] == round(call["responseBytes"] / 4)


def test_rejected_arguments_logged_with_suggestion():
    with pytest.raises(Exception):
        anyio.run(server.mcp.call_tool, "resolve_bug", {"issueKey": "OOP-1"})
    call = _rows("calls")[0]
    error = _rows("errors")[0]
    assert (call["tool"], call["status"]) == ("resolve_bug", "invalid_arguments")
    assert error["kind"] == "arg_error"
    assert error["unknown"] == ["issueKey"] and error["missingRequired"] == ["issue_key"]
    assert error["suggested"] == {"issueKey": "issue_key"}


def test_tool_call_logs_only_client_sent_arguments():
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value={"dryRun": True, "warnings": []}), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}):
        anyio.run(server.mcp.call_tool, "resolve_bug", {"issue_key": "OOP-1", "commit": "abc"})
    assert _details()[0]["arguments"] == {"issue_key": "OOP-1", "commit": "abc"}


def test_metrics_and_workflow_resources_are_gone():
    resources = anyio.run(server.mcp.list_resources)
    uris = {str(resource.uri) for resource in resources}
    assert "backlog://metrics" not in uris and "backlog://workflow-efficiency" not in uris
```

  - Sửa các test còn gọi `server._build_result(..., started=...)` / `server._error_result(..., started=...)` (dòng ~118, ~167): bỏ đối số `started=`.

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_mcp_server.py -q`
Expected: FAIL (`log_metric` import lỗi / `started` unexpected / không có `calls.jsonl`).

- [ ] **Step 3: Sửa `backlog_mcp/results.py`**
  - Import: thay khối import từ `backlog_tool.settings` và `backlog_tool.telemetry` bằng:

```python
from backlog_tool.telemetry import current_trace_id, finish_call, serialized_bytes
```

  - `_error_result(tool, error, dry_run=None, project=None, status="error")`: giữ phần dựng `text`, `response_shape`, `total_bytes`; thay toàn bộ khối `if started is not None: …` và `clear_trace()` bằng:

```python
    trace_id = current_trace_id() or ""
    finish_call(
        status,
        result=None,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode=None if dry_run is None else ("preview" if dry_run else "apply"),
        error=message,
    )
```

    và `_meta={"tool": tool, "command": tool, "traceId": trace_id}`.
  - `_build_result(data, tool, list_key=None, limit=0, offset=0, paginated=False, dry_run=None, project=None)`: `trace_id = current_trace_id() or ""` thay cho `ensure_trace(tool)`; thay khối `if started is not None: …` và `clear_trace()` bằng:

```python
    finish_call(
        "ok",
        result=envelope_data,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode=None if dry_run is None else ("preview" if dry_run else "apply"),
    )
```

  - `_partial_write_result(tool, message, data, project=None)`: `trace_id = current_trace_id() or ""`; thay khối log bằng:

```python
    finish_call(
        "partial_write",
        result=structured,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode="apply",
        error=message,
    )
```

  - Xoá `import time` nếu không còn dùng.

- [ ] **Step 4: Sửa `backlog_mcp/server.py`**
  - Import: `from backlog_tool.telemetry import begin_tool_trace, reset_client_arguments, set_client_arguments` → `from backlog_tool.telemetry import log_session_start, record_arg_error, reset_client_arguments, set_client_arguments, start_call`; thêm `from .arg_errors import describe_validation_error`; xoá import `summarize_metrics` (khối import từ `backlog_tool.settings`) và `from backlog_tool.workflow_efficiency import summarize_workflow_efficiency`.
  - Đổi mọi `begin_tool_trace(` thành `start_call(`:

Run: `sed -i 's/begin_tool_trace(/start_call(/g' backlog_mcp/server.py`

  - Xoá mọi dòng `started = time.monotonic()` và mọi đối số `started=started` / `started=started,`:

Run: `sed -i '/^\s*started = time\.monotonic()$/d; s/,\s*started=started//g; s/started=started,\s*//g' backlog_mcp/server.py`
Rồi: `grep -n "started" backlog_mcp/server.py` — Expected: không còn kết quả; nếu còn dòng `started=started` đứng riêng (một đối số trên một dòng), xoá dòng đó bằng tay.

  - Wrapper `_record_rejected_tool_calls` — thay khối `except ToolError as error:` bằng:

```python
        except ToolError as error:
            cause = error.__cause__
            status = "invalid_arguments" if isinstance(cause, ValidationError) else "rejected"
            start_call(name, arguments)
            if isinstance(cause, ValidationError):
                tool = manager.get_tool(name)
                valid = list((tool.parameters or {}).get("properties", {})) if tool else []
                record_arg_error(name, arguments, describe_validation_error(cause, valid))
            _error_result(name, error, status=status)
            raise
```

    và xoá dòng `started = time.monotonic()` trong wrapper.
  - Xoá hai resource `metrics_resource` và `workflow_efficiency_resource` (cả decorator).
  - `main()`:

```python
def main() -> None:
    """Run the workstation-local server over stdio."""
    tools = anyio.run(mcp.list_tools)
    log_session_start(backend="real", workspace=_workspace_path() or os.getcwd(), tool_count=len(tools))
    mcp.run(transport="stdio")
```

    và thêm `import anyio` vào đầu file. Xoá `import time` nếu không còn dùng.

- [ ] **Step 5: Chạy test**

Run: `uv run --extra dev pytest tests/test_mcp_server.py tests/test_telemetry.py tests/test_arg_errors.py -q`
Expected: PASS.

### Task 4: API call và mutation

**Files:**
- Modify: `backlog_tool/client.py`
- Modify: `backlog_tool/issue_service.py:219-221, 358-360`
- Modify: `workflows/ut_bug.py:133-142`
- Modify: `workflows/resolve_bug.py` (`resolve_bug`)
- Modify: `tests/test_backlog_api.py`, `tests/test_bug_workflow.py`, `tests/test_create_ut_bug_default.py`

**Interfaces:**
- Consumes: `record_api_call`, `record_mutation`, `plan_hash`, `start_call`, `finish_call`, `log_paths` (Task 2).
- Produces: mọi tool ghi (`create_issue`, `update_issue`, `create_ut_bug`, `resolve_bug`) để lại `details.mutation = {mode, planHash, changedFields, …}`; `resolve_bug` thêm `statusBefore`, `statusAfter` (apply), `warnings`.

- [ ] **Step 1: Viết test fail** — thêm vào `tests/test_bug_workflow.py` (class `BugWorkflowTest`), và xoá dòng `mock.patch.object(bug_workflow, "log_event").start()` trong `setUp`:

```python
    def test_resolve_records_mutation_for_preview_and_apply(self):
        from backlog_tool import telemetry

        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        telemetry.start_call("resolve_bug", {"issue_key": "AQM-123"})
        preview = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="x")
        telemetry.start_call("resolve_bug", {"issue_key": "AQM-123", "mode": "apply"})
        with mock.patch.object(bug_workflow, "record_mutation") as record:
            bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2), fix_description="x")
        telemetry.finish_call("ok")

        applied = record.call_args.kwargs
        self.assertEqual("apply", applied["mode"])
        self.assertEqual(telemetry.plan_hash("AQM-123", preview["payload"]), applied["planHash"])
        self.assertEqual("In Progress", applied["statusBefore"])
        self.assertEqual("Resolved", applied["statusAfter"])
        self.assertIn("statusId", applied["changedFields"])
```

Thêm vào `tests/test_backlog_api.py`: xoá dòng `mock.patch.object(backlog_issue_service, "log_event").start()` (dòng ~116); thay test `test_log_response_records_error_status_and_body_without_url` bằng:

```python
    def test_request_json_records_api_call_without_query_or_key(self):
        from backlog_tool import telemetry

        class Response:
            ok = False
            status_code = 400
            text = '{"errors":[{"message":"bad request"}]}'

            def raise_for_status(self):
                raise backlog_client.requests.HTTPError("bad")

        with mock.patch.object(backlog_client, "require_api_key", return_value="SECRET"), \
             mock.patch.object(backlog_client, "api_base_url", return_value="https://x/api/v2"), \
             mock.patch.object(backlog_client.requests, "request", return_value=Response()):
            telemetry.start_call("create_issue", {})
            with self.assertRaises(RuntimeError):
                backlog_client.BacklogClient({}).request_json("POST", "/issues", params={"count": 1})
            telemetry.finish_call("error", error="bad request")

        folder = telemetry.log_paths()["details_dir"]
        text = "".join(open(os.path.join(folder, n), encoding="utf-8").read() for n in os.listdir(folder))
        errors = open(telemetry.log_paths()["errors"], encoding="utf-8").read()
        self.assertNotIn("SECRET", text + errors)
        self.assertIn('"path": "/issues"', text)
        self.assertIn('"kind": "api_error"', errors)
```

(Thêm `import os` nếu file chưa có.) Trong `tests/test_create_ut_bug_default.py` xoá dòng `mock.patch.object(backlog_ut_bug_service, "log_event").start()`.

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_bug_workflow.py tests/test_backlog_api.py tests/test_create_ut_bug_default.py -q`
Expected: FAIL (`record_mutation` không tồn tại trong `bug_workflow`; `log_response` còn dùng `log_event`).

- [ ] **Step 3: `backlog_tool/client.py`** — xoá hàm `log_response`; import:

```python
from .settings import REQUEST_TIMEOUT_SECONDS, api_base_url, require_api_key, response_error_body
from .telemetry import record_api_call, serialized_bytes
```

Thay thân `request_json` từ sau `response = requests.request(...)`:

```python
        duration_ms = (time.monotonic() - started) * 1000
        record_api_call(
            method,
            path,
            response.status_code,
            response.ok,
            duration_ms,
            serialized_bytes(request_body),
            len((response.text or "").encode("utf-8")),
            response.text,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RuntimeError(
                f"{method} {path} failed with status {response.status_code}: {response_error_body(response)}"
            ) from error
        return response.json()
```

và xoá dòng `trace_id = ensure_trace()`.

- [ ] **Step 4: Mutation ở service/workflow**
  - `backlog_tool/issue_service.py`: import `from .telemetry import plan_hash, record_mutation` (bỏ `log_event` khỏi import settings). Thay khối dry-run của create:

```python
    record_mutation(
        mode="preview" if dry_run else "apply",
        planHash=plan_hash(None, data),
        changedFields=sorted(data.keys()),
    )
    if dry_run:
        return {"dryRun": True, "payload": data}
```

    và của update:

```python
    record_mutation(
        mode="preview" if dry_run else "apply",
        planHash=plan_hash(target_id, data),
        changedFields=sorted(data.keys()),
    )
    if dry_run:
        return {"dryRun": True, "issue": target_id, "payload": data}
```

  - `workflows/ut_bug.py`: import `from backlog_tool.telemetry import plan_hash, record_mutation` (bỏ `log_event`); thay khối `if dry_run: log_event(...)`:

```python
    record_mutation(
        mode="preview" if dry_run else "apply",
        planHash=plan_hash(parent_key, built["payload"]),
        changedFields=sorted(built["payload"].keys()),
    )
    if dry_run:
        return {"dryRun": True, **built}
```

  - `workflows/resolve_bug.py`: import `from backlog_tool.telemetry import plan_hash, record_mutation` (bỏ `log_event` khỏi import settings). Thay phần sau `built = build_resolve_bug_payload(...)` trong `resolve_bug`:

```python
    outcome = {
        "planHash": plan_hash(issue_key, built["payload"]),
        "statusBefore": built["context"].get("status"),
        "changedFields": sorted(built["payload"].keys()),
        "warnings": built["warnings"],
    }
    if dry_run:
        record_mutation(mode="preview", **outcome)
        return {"dryRun": True, **built}
    updated = BacklogClient(config).update_issue(issue_key, built["payload"])
    record_mutation(mode="apply", statusAfter=((updated or {}).get("status") or {}).get("name"), **outcome)
    return updated
```

- [ ] **Step 5: Chạy test**

Run: `uv run --extra dev pytest tests/test_bug_workflow.py tests/test_backlog_api.py tests/test_create_ut_bug_default.py -q`
Expected: PASS.

### Task 5: CLI trace, xoá sink cũ

**Files:**
- Modify: `backlog_tool/cli.py`
- Modify: `backlog_tool/settings.py`
- Delete: `backlog_tool/journal.py`, `tests/test_metrics.py`
- Modify: `tests/test_backlog_settings.py` (xoá test log_event), `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2 API.
- Produces: `cli.CLI_TOOL_NAMES: dict[str, str]`, `cli.cli_trace_arguments(args) -> dict`. Mỗi lệnh CLI ghi 1 dòng `sessions` + 1 call (`surface: "cli"`).

- [ ] **Step 1: Viết test fail** — thêm vào `tests/test_cli.py`:

```python
import json as _json
import os as _os
from unittest import mock as _mock

from backlog_tool import telemetry


class CliTelemetryTest(unittest.TestCase):
    def _rows(self, kind):
        with open(telemetry.log_paths()[kind], encoding="utf-8") as handle:
            return [_json.loads(line) for line in handle if line.strip()]

    def test_cli_command_traced_under_mcp_tool_name(self):
        with _mock.patch.object(cli, "load_config", return_value={"base_url": "https://x"}), \
             _mock.patch.object(cli, "run_handler", return_value={"dryRun": True, "issue": "OOP-1"}), \
             _mock.patch.object(cli, "resolve_project_key_for_issue", return_value="OOP"):
            cli.execute(["bug", "resolve", "OOP-1"])
        [call] = self._rows("calls")
        [session] = self._rows("sessions")
        self.assertEqual(("resolve_bug", "cli", "ok", "preview"), (call["tool"], call["surface"], call["status"], call["mode"]))
        self.assertEqual("cli", session["surface"])
        folder = telemetry.log_paths()["details_dir"]
        detail = _json.loads(open(_os.path.join(folder, _os.listdir(folder)[0]), encoding="utf-8").readline())
        self.assertEqual("OOP-1", detail["arguments"]["issue_key"])

    def test_cli_error_closes_trace(self):
        with _mock.patch.object(cli, "load_config", side_effect=ValueError("bad config")):
            with self.assertRaises(ValueError):
                cli.execute(["bug", "context", "OOP-1"])
        [call] = self._rows("calls")
        self.assertEqual(("get_bug_context", "error"), (call["tool"], call["status"]))
        self.assertEqual("bad config", self._rows("errors")[0]["message"])
        self.assertIsNone(telemetry.current_trace_id())
```

Trước Step 3, kiểm tra tên thuộc tính argparse: `uv run python -c "from backlog_tool import cli; print(vars(cli.build_parser().parse_args(['bug','resolve','OOP-1'])))"` — nếu mã issue nằm ở thuộc tính khác `issue_key` (ví dụ `issue_id`), sửa assert `detail["arguments"][...]` cho đúng tên thật.

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `uv run --extra dev pytest tests/test_cli.py -q -k CliTelemetry`
Expected: FAIL (`FileNotFoundError` cho `calls.jsonl`).

- [ ] **Step 3: Sửa `backlog_tool/cli.py`**
  - Xoá `from backlog_tool import journal`; bỏ `log_event`, `log_metric` khỏi import settings; thêm:

```python
from backlog_tool.telemetry import finish_call, log_session_start, set_surface, start_call
```

  - Thêm sau `is_dry_run`:

```python
# CLI commands are logged under the equivalent MCP tool name so both surfaces
# read as one workflow in telemetry.
CLI_TOOL_NAMES = {
    "issue:get": "get_issue",
    "issue:list": "get_issues",
    "issue:create": "create_issue",
    "issue:update": "update_issue",
    "bug:list": "get_my_open_bugs",
    "bug:context": "get_bug_context",
    "bug:resolve": "resolve_bug",
    "bug:create-ut": "create_ut_bug",
    "bug:rules": "get_bug_rules",
    "bug:fields": "get_bug_fields",
}
_UNTRACED_ARGS = {"group", "action", "json_full", "table", "workspace_path", "apply"}


def cli_trace_arguments(args):
    arguments = {
        key: value
        for key, value in vars(args).items()
        if key not in _UNTRACED_ARGS and value not in (None, False, "", [])
    }
    dry_run = is_dry_run(args)
    if dry_run is not None:
        arguments["mode"] = "preview" if dry_run else "apply"
    return arguments
```

  - Trong `execute`, ngay sau `dry_run = is_dry_run(args)`:

```python
    set_surface("cli")
    log_session_start(backend="real", workspace=workspace_path or os.getcwd())
    start_call(CLI_TOOL_NAMES.get(name, name), cli_trace_arguments(args))
    try:
        config = load_config()
    except Exception as error:
        finish_call("error", error=str(error))
        raise
```

    và xoá dòng `config = load_config()` cũ. Thêm `import os` ở đầu file.
  - Xoá mọi dòng `log_event(...)` (command_start, command_end, issue_created, command_error), `log_metric(...)` (2 chỗ), `journal.log_cli(...)` (và khối `if args.group in ("issue", "bug", "story"):` bao quanh nó), `started = time.monotonic()` và `duration_ms = ...` nếu không còn dùng.
  - Ở nhánh thành công, ngay trước `return CommandResult(...)`:

```python
        finish_call(
            "ok",
            result=presented_data,
            text=text,
            response_bytes=len(text.encode("utf-8")),
            project_key=project,
        )
```

  - Ở nhánh `except Exception as error:` ngay trước `raise`:

```python
        finish_call("error", error=str(error), project_key=project)
```

  - Xoá `import time` nếu không còn dùng.

- [ ] **Step 4: Sửa `backlog_tool/settings.py`** — (đồng thời trong `tests/conftest.py` xoá khối "Transitional…" cùng khối `try: from backlog_tool import journal`) — xoá `LOG_PATH`, `METRICS_PATH`, `TELEMETRY_PATH`, hàm `log_event`, `log_metric`, `read_metrics`, `summarize_metrics`. Giữ `LOG_DIR`, `MAX_LOG_VALUE_LENGTH`, `response_error_body`, `rotate_file_if_needed`, `report_log_failure`, `_reported_log_failures`. Xoá `backlog_tool/journal.py`, `tests/test_metrics.py`; trong `tests/test_backlog_settings.py` xoá test `test_log_event_writes_timestamped_redacted_shape_without_newline_leak`.

- [ ] **Step 5: Tìm sót**

Run: `grep -rnE "log_event|log_metric|journal|log_telemetry|begin_tool_trace|ensure_trace|clear_trace|METRICS_PATH|LOG_PATH|TELEMETRY_PATH|summarize_metrics|read_metrics" backlog_mcp backlog_tool workflows tests`
Expected: chỉ còn `backlog_tool/workflow_efficiency.py` và `tests/test_workflow_efficiency.py` (xoá ở Task 8). `workflow_efficiency.py` đọc `settings.TELEMETRY_PATH` bên trong hàm — sửa dòng `path = settings.TELEMETRY_PATH` thành `path = os.path.join(settings.LOG_DIR, "telemetry.jsonl")` để module vẫn import được cho tới Task 8.

- [ ] **Step 6: Chạy toàn bộ test + lint**

Run: `uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows`
Expected: PASS; `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add -A backlog_mcp backlog_tool workflows tests
git commit -m "Replace legacy log sinks with calls/errors/sessions/details telemetry

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 6: `docs/telemetry.md`, README, kiểm chứng trên dùng thật (đóng P1)

**Files:**
- Create: `docs/telemetry.md`
- Modify: `README.md` (mục "Local State", "Workflow Efficiency Analysis", "Telemetry", bảng resources)

- [ ] **Step 1: Viết `docs/telemetry.md`**

````markdown
# Backlog MCP telemetry

Đọc file này trước khi phân tích log. Log nằm trong `logs/` (hoặc `$BACKLOG_MCP_LOG_DIR`).

## File

| File | Một dòng là | Dùng để |
|---|---|---|
| `calls.jsonl` | một tool call (MCP hoặc CLI) | quét nhanh: tool nào, bao lâu, bao nhiêu token, lỗi gì |
| `errors.jsonl` | một lỗi (`tool_error`, `arg_error`, `api_error`, `partial_write`) | tìm lỗi lặp lại |
| `sessions.jsonl` | một process (MCP server hoặc lệnh CLI) | phiên bản code (`gitSha`), client, backend real/fake |
| `details/YYYY-MM-DD.jsonl` | chi tiết một tool call | xem `arguments`, `result`, `text`, API call, `mutation` |

Mọi dòng nối với nhau bằng `traceId` (call) và `sessionId` (process). Quy trình đọc chuẩn: quét `calls.jsonl` và `errors.jsonl` trước; chỉ mở `details/` bằng `traceId` khi cần nội dung đầy đủ.

## Field chung
`v` (3), `ts`, `sessionId`, `surface` (`mcp`|`cli`), `client {name, version}`, `runId`/`scenario` (chỉ khi eval).

## calls.jsonl
`traceId, tool, argKeys, issueKey, projectKey, mode, status (ok|error|invalid_arguments|rejected|partial_write), durationMs, apiCalls, apiMs, responseBytes, estTokens (= responseBytes/4, ước lượng), flags`.

## errors.jsonl
`traceId, kind, tool, message` và theo `kind`:
- `arg_error`: `sent`, `unknown`, `missingRequired`, `invalid [{name, reason}]`, `suggested {sai: đúng}`.
- `api_error`: `method, path, status, body` (≤ 2 KB).

## details/
`traceId, tool, arguments (đúng như client gửi), result (structuredContent), text (text content), api [{method, path, status, durationMs, requestBytes, responseBytes, body?}], mutation {mode, planHash, statusBefore, statusAfter, changedFields, warnings}`.
`api[].body` chỉ có khi lỗi hoặc method ≠ GET; `BACKLOG_MCP_LOG_BODIES=full` để giữ mọi body. File `details/` giữ 30 ngày.

## Công thức mẫu
```bash
# Top tool theo token trong ngày
jq -s 'map(select(.ts >= "2026-09-24")) | group_by(.tool) | map({tool: .[0].tool, calls: length, tokens: (map(.estTokens) | add)}) | sort_by(-.tokens)' logs/calls.jsonl
# Lỗi tham số lặp lại
jq -s 'map(select(.kind == "arg_error")) | group_by([.tool, (.unknown | join(","))]) | map({tool: .[0].tool, unknown: .[0].unknown, suggested: .[0].suggested, count: length}) | sort_by(-.count)' logs/errors.jsonl
# Xem đầy đủ một call
grep -h '"traceId": "<id>"' logs/details/*.jsonl | jq .
# Chuỗi tool của một session
jq -c 'select(.sessionId == "<id>") | [.ts, .tool, .status, .estTokens]' logs/calls.jsonl
# Call chậm nhất
jq -s 'sort_by(-.durationMs) | .[:10] | map({ts, tool, durationMs, apiMs})' logs/calls.jsonl
```

## Báo cáo có sẵn
`uv run backlog-cli telemetry report --since 1d [--run <runId>] [--json]` — flow, rule, chấm kịch bản, field thiếu (xem Plan A Task 12).
`uv run backlog-cli telemetry import-claude --since 1d` — ghép transcript Claude Code.

## Log cũ
Log trước 2026-09-24 (`backlog.log`, `metrics.log`, `telemetry.jsonl*`, `sessions/`) không được công cụ mới đọc. Chuyển một lần:
```bash
mkdir -p logs/legacy && mv logs/backlog.log* logs/metrics.log* logs/telemetry.jsonl* logs/sessions logs/legacy/ 2>/dev/null
```
````

- [ ] **Step 2: README** — mục "Local State": thay 4 dòng trong `logs/` bằng `calls.jsonl`, `errors.jsonl`, `sessions.jsonl`, `details/` và dòng "See docs/telemetry.md". Xoá bảng dòng `backlog://metrics`, `backlog://workflow-efficiency`. Thay mục "Workflow Efficiency Analysis" và "Telemetry" bằng một đoạn: "Telemetry schema, reading guide and recipes: docs/telemetry.md. Set `BACKLOG_MCP_LOG_DIR` to write logs elsewhere."

- [ ] **Step 3: Commit + push**

```bash
git add docs/telemetry.md README.md
git commit -m "Document telemetry layout and reading recipes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

- [ ] **Step 4: Kiểm chứng dùng thật (điều kiện đóng P1)** — nhờ người dùng chạy lệnh chuyển log cũ (docs/telemetry.md §Log cũ), restart client MCP, dùng bình thường ≥ 1 buổi, rồi chạy:

```bash
uv run python - <<'EOF'
import json, os
from backlog_tool import telemetry
p = telemetry.log_paths()
calls = [json.loads(l) for l in open(p["calls"])]
details = []
for n in os.listdir(p["details_dir"]):
    details += [json.loads(l) for l in open(os.path.join(p["details_dir"], n))]
sessions = [json.loads(l) for l in open(p["sessions"])]
print("calls", len(calls), "details", len(details), "sessions", len(sessions))
print("calls without detail:", len({c["traceId"] for c in calls} - {d["traceId"] for d in details}))
print("sessions gitSha:", sorted({s.get("gitSha") for s in sessions}))
print("surfaces:", sorted({c["surface"] for c in calls}), "clients:", sorted({c["client"]["name"] for c in calls}))
EOF
```

Expected: `calls without detail: 0`; `gitSha` = `git rev-parse --short HEAD`; có client thật (`claude-code`, `antigravity…`). Ghi kết quả vào mô tả commit kế tiếp hoặc báo người dùng. P1 đóng khi đạt.

---

## Phase P2 — Phân tích

### Task 7: `telemetry_store` — đọc log và dựng flow

**Files:**
- Create: `backlog_tool/telemetry_store.py`
- Test: `tests/test_telemetry_store.py`

**Interfaces:**
- Consumes: bố cục log Task 2.
- Produces:
  - `@dataclass Call(trace_id, ts, tool, arguments, status, duration_ms, api_calls, response_bytes, est_tokens, client, session_id, surface, run_id, scenario, issue_key, project_key, result=None, text=None, mutation=None, errors=list)`
  - `@dataclass Flow(flow_id, calls: list[Call], prompt=None, final_answer=None, non_mcp=list, schema_reads=0, denied=list, model=None, client=None, wall_clock_ms=None, startup_ms=None)` với property `tools -> list[str]`, `started_at -> str | None`
  - `load_calls(log_dir=None, since=None, run_id=None) -> list[Call]` (join `calls` + `details` + `errors`; đọc cả `calls.jsonl.1..5`)
  - `group_flows(calls, gap_seconds=180) -> list[Flow]` (theo `runId` nếu có; ngược lại heuristic)

- [ ] **Step 1: Viết test fail** — `tests/test_telemetry_store.py`:

```python
from backlog_tool import telemetry
from backlog_tool.telemetry_store import group_flows, load_calls


def make_call(tool, args, result=None, status="ok"):
    telemetry.start_call(tool, args)
    if status == "ok":
        telemetry.finish_call("ok", result=result or {}, text="t", response_bytes=40)
    else:
        telemetry.finish_call(status, text="Error", response_bytes=10, error="boom")


def test_load_calls_joins_index_details_and_errors():
    make_call("get_bug_context", {"issue_key": "OOP-1"}, {"ok": True, "data": {"summary": "S"}})
    make_call("get_issue", {"issue_ref": "OOP-1"}, status="error")
    calls = load_calls()
    assert [c.tool for c in calls] == ["get_bug_context", "get_issue"]
    assert calls[0].result == {"ok": True, "data": {"summary": "S"}}
    assert calls[0].issue_key == "OOP-1" and calls[1].issue_key == "OOP-1"
    assert calls[1].errors[0]["message"] == "boom"


def test_load_calls_filters_by_since_and_run():
    telemetry.set_eval_tags("run-a", "open_bugs")
    make_call("get_my_open_bugs", {})
    telemetry.set_eval_tags("run-b", "open_bugs")
    make_call("get_my_open_bugs", {})
    telemetry.set_eval_tags(None, None)
    assert len(load_calls(run_id="run-a")) == 1
    assert load_calls(since="2999-01-01") == []


def test_group_flows_by_run_id():
    telemetry.set_eval_tags("run-a", "resolve_fixed")
    make_call("resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    telemetry.set_eval_tags("run-b", "resolve_fixed")
    make_call("resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    telemetry.set_eval_tags(None, None)
    flows = group_flows(load_calls())
    assert [f.flow_id for f in flows] == ["run-a", "run-b"]


def test_group_flows_heuristic_splits_on_issue_session_and_gap():
    make_call("get_bug_context", {"issue_key": "OOP-1"})
    make_call("get_issue", {"issue_ref": "OOP-1"})
    make_call("get_bug_context", {"issue_key": "OOP-2"})
    calls = load_calls()
    flows = group_flows(calls)
    assert [f.tools for f in flows] == [["get_bug_context", "get_issue"], ["get_bug_context"]]

    calls[1].session_id = "other"
    assert len(group_flows(calls)) == 3

    calls[1].session_id = calls[0].session_id
    calls[1].ts = "2999-01-01T00:00:00.000+07:00"
    assert len(group_flows(calls)) == 3
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_telemetry_store.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Viết `backlog_tool/telemetry_store.py`**

```python
"""Read telemetry files into calls and group them into flows (one user request ≈ one flow)."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from . import settings


@dataclass
class Call:
    trace_id: str
    ts: str
    tool: str
    arguments: dict
    status: str
    duration_ms: float
    api_calls: int
    response_bytes: int
    est_tokens: int
    client: str
    session_id: str
    surface: str
    run_id: str | None
    scenario: str | None
    issue_key: str | None
    project_key: str | None
    result: object = None
    text: str | None = None
    mutation: dict | None = None
    errors: list = field(default_factory=list)


@dataclass
class Flow:
    flow_id: str
    calls: list
    prompt: str | None = None
    final_answer: str | None = None
    non_mcp: list = field(default_factory=list)
    schema_reads: int = 0
    denied: list = field(default_factory=list)
    model: str | None = None
    client: str | None = None
    wall_clock_ms: float | None = None
    startup_ms: float | None = None

    @property
    def tools(self):
        return [call.tool for call in self.calls]

    @property
    def started_at(self):
        return self.calls[0].ts if self.calls else None


def _read_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _rotated(path):
    return [f"{path}.{index}" for index in range(5, 0, -1)] + [path]


def load_calls(log_dir=None, since=None, run_id=None):
    log_dir = log_dir or settings.LOG_DIR
    index = [row for path in _rotated(os.path.join(log_dir, "calls.jsonl")) for row in _read_jsonl(path)]
    if since:
        index = [row for row in index if (row.get("ts") or "") >= since]
    if run_id:
        index = [row for row in index if row.get("runId") == run_id]
    wanted = {row["traceId"] for row in index}

    details = {}
    details_dir = os.path.join(log_dir, "details")
    if os.path.isdir(details_dir):
        for name in sorted(os.listdir(details_dir)):
            if since and name[:10] < since[:10]:
                continue
            for row in _read_jsonl(os.path.join(details_dir, name)):
                if row.get("traceId") in wanted:
                    details[row["traceId"]] = row

    errors = {}
    for path in _rotated(os.path.join(log_dir, "errors.jsonl")):
        for row in _read_jsonl(path):
            if row.get("traceId") in wanted:
                errors.setdefault(row["traceId"], []).append(row)

    calls = []
    for row in sorted(index, key=lambda item: item.get("ts") or ""):
        detail = details.get(row["traceId"], {})
        calls.append(Call(
            trace_id=row["traceId"],
            ts=row.get("ts") or "",
            tool=row.get("tool") or "unknown",
            arguments=detail.get("arguments") or {},
            status=row.get("status") or "unknown",
            duration_ms=row.get("durationMs") or 0,
            api_calls=row.get("apiCalls") or 0,
            response_bytes=row.get("responseBytes") or 0,
            est_tokens=row.get("estTokens") or 0,
            client=(row.get("client") or {}).get("name") or "unknown",
            session_id=row.get("sessionId") or "",
            surface=row.get("surface") or "mcp",
            run_id=row.get("runId"),
            scenario=row.get("scenario"),
            issue_key=row.get("issueKey"),
            project_key=row.get("projectKey"),
            result=detail.get("result"),
            text=detail.get("text"),
            mutation=detail.get("mutation"),
            errors=errors.get(row["traceId"], []),
        ))
    return calls


def _seconds_between(earlier, later):
    try:
        return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _fits(flow, call, gap_seconds):
    last = flow.calls[-1]
    if last.session_id != call.session_id:
        return False
    if _seconds_between(last.ts, call.ts) > gap_seconds:
        return False
    issues = {c.issue_key for c in flow.calls if c.issue_key}
    if call.issue_key and issues and call.issue_key not in issues:
        return False
    projects = {c.project_key for c in flow.calls if c.project_key}
    if call.project_key and projects and call.project_key not in projects:
        return False
    return True


def group_flows(calls, gap_seconds=180):
    by_run = {}
    heuristic = []
    for call in calls:
        if call.run_id:
            by_run.setdefault(call.run_id, Flow(call.run_id, [], client=call.client)).calls.append(call)
        else:
            heuristic.append(call)

    flows = list(by_run.values())
    open_flows = []
    for call in heuristic:
        target = next((flow for flow in reversed(open_flows) if _fits(flow, call, gap_seconds)), None)
        if target is None:
            target = Flow(f"flow-{call.trace_id[:8]}", [], client=call.client)
            open_flows.append(target)
        target.calls.append(call)
    flows.extend(open_flows)
    flows.sort(key=lambda flow: flow.started_at or "")
    return flows
```

- [ ] **Step 4: Chạy test** — `uv run --extra dev pytest tests/test_telemetry_store.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backlog_tool/telemetry_store.py tests/test_telemetry_store.py
git commit -m "Load telemetry into calls and group them into flows

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 8: `telemetry_rules` — rule chung (tầng 2), thay `workflow_efficiency`

**Files:**
- Create: `backlog_tool/telemetry_rules.py`
- Test: `tests/test_telemetry_rules.py`
- Delete: `backlog_tool/workflow_efficiency.py`, `tests/test_workflow_efficiency.py`

**Interfaces:**
- Consumes: `Call`, `Flow` (Task 7).
- Produces: `apply_rules(flow: Flow) -> list[dict]`; mỗi finding `{"code", "severity": "warning"|"candidate"|"info", "reason", "traceIds": [..]}`. Codes: `duplicate_call`, `generic_after_specialized`, `generic_before_specialized`, `arg_error`, `retry_after_error`, `large_response`. (`missing_field` được thêm ở Task 10.)

- [ ] **Step 1: Viết test fail** — `tests/test_telemetry_rules.py`:

```python
from backlog_tool.telemetry_rules import apply_rules
from backlog_tool.telemetry_store import Call, Flow


def call(tool, args, status="ok", trace=None, response_bytes=100, errors=None, issue=None):
    return Call(
        trace_id=trace or f"{tool}-{len(str(args))}-{status}",
        ts="2026-09-24T10:00:00.000+07:00", tool=tool, arguments=args, status=status,
        duration_ms=1, api_calls=1, response_bytes=response_bytes, est_tokens=response_bytes // 4,
        client="c", session_id="s", surface="mcp", run_id=None, scenario=None,
        issue_key=issue or args.get("issue_key") or args.get("issue_ref"), project_key="OOP",
        errors=errors or [],
    )


def codes(flow):
    return sorted(f["code"] for f in apply_rules(flow))


def test_duplicate_and_generic_after_specialized():
    flow = Flow("f", [
        call("get_bug_context", {"issue_key": "OOP-1"}, trace="a"),
        call("get_issue", {"issue_ref": "OOP-1"}, trace="b"),
        call("get_bug_context", {"issue_key": "OOP-1"}, trace="c"),
    ])
    assert codes(flow) == ["duplicate_call", "generic_after_specialized", "generic_before_specialized"]


def test_generic_search_before_personal_bugs():
    flow = Flow("f", [call("get_issues", {"project_key": "OOP"}), call("get_my_open_bugs", {})])
    assert codes(flow) == ["generic_before_specialized"]


def test_arg_error_retry_and_large_response():
    flow = Flow("f", [
        call("resolve_bug", {"issueKey": "OOP-1"}, status="invalid_arguments", issue="OOP-1",
             errors=[{"kind": "arg_error", "unknown": ["issueKey"]}], trace="x"),
        call("resolve_bug", {"issue_key": "OOP-1"}, trace="y", response_bytes=9000),
    ])
    assert codes(flow) == ["arg_error", "large_response", "retry_after_error"]


def test_clean_fast_path_has_no_findings():
    assert codes(Flow("f", [call("resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})])) == []
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError`.

- [ ] **Step 3: Viết `backlog_tool/telemetry_rules.py`**

```python
"""Tier-2 rules: observable inefficiencies that apply to every flow, with or without a scenario."""

import json

from .telemetry import LARGE_RESPONSE_BYTES

# (generic tool, specialized tool) pairs where the specialized tool is the intended path.
SPECIALIZED = [("get_issue", "get_bug_context"), ("get_issues", "get_my_open_bugs")]


def _finding(code, reason, calls, severity="warning"):
    return {"code": code, "severity": severity, "reason": reason, "traceIds": [c.trace_id for c in calls]}


def _same_subject(a, b):
    return a.issue_key == b.issue_key or not (a.issue_key and b.issue_key)


def apply_rules(flow):
    calls = flow.calls
    findings = []

    seen = {}
    for call in calls:
        key = (call.tool, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False))
        if key in seen:
            findings.append(_finding("duplicate_call", f"{call.tool} repeated with identical arguments.", [seen[key], call]))
        else:
            seen[key] = call

    for generic, specialized in SPECIALIZED:
        for i, call in enumerate(calls):
            if call.tool != generic:
                continue
            before = [c for c in calls[:i] if c.tool == specialized and _same_subject(c, call)]
            after = [c for c in calls[i + 1:] if c.tool == specialized and _same_subject(c, call)]
            if before:
                findings.append(_finding(
                    "generic_after_specialized",
                    f"{generic} followed {specialized}; the specialized response may be missing data or the routing is unclear.",
                    [before[-1], call], severity="candidate",
                ))
            if after:
                findings.append(_finding(
                    "generic_before_specialized",
                    f"{generic} preceded {specialized}; {specialized} is the direct path.",
                    [call, after[0]],
                ))

    for i, call in enumerate(calls):
        if any(error.get("kind") == "arg_error" for error in call.errors):
            findings.append(_finding("arg_error", f"{call.tool} was called with invalid arguments.", [call]))
        if call.status != "ok" and i + 1 < len(calls) and calls[i + 1].tool == call.tool:
            findings.append(_finding("retry_after_error", f"{call.tool} retried after status {call.status}.", [call, calls[i + 1]], severity="info"))
        if call.response_bytes > LARGE_RESPONSE_BYTES:
            findings.append(_finding("large_response", f"{call.tool} returned {call.response_bytes} bytes.", [call], severity="info"))

    return findings
```

- [ ] **Step 4: Xoá analyzer cũ** — `git rm backlog_tool/workflow_efficiency.py tests/test_workflow_efficiency.py`; `grep -rn workflow_efficiency backlog_mcp backlog_tool tests` → không còn kết quả.

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add -A backlog_tool tests
git commit -m "Add tier-2 telemetry rules and retire workflow_efficiency

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 9: Kịch bản và bộ chấm (tầng 3)

**Files:**
- Create: `evals/__init__.py` (rỗng), `evals/scenarios.json`
- Create: `backlog_tool/telemetry_grader.py`
- Test: `tests/test_telemetry_grader.py`

**Interfaces:**
- Consumes: `Flow`, `Call` (Task 7).
- Produces:
  - `load_scenarios(path=None) -> list[dict]` (mặc định `<repo>/evals/scenarios.json`)
  - `render_scenario(scenario: dict) -> dict` (thay `{issue}`… bằng `fixtures` trong `prompt` và `expect.calls[].args`)
  - `match_prompt(prompt: str, scenarios: list[dict]) -> tuple[dict, list[str]] | None` (kịch bản + danh sách mã issue)
  - `expect_for(scenario: dict, issue_keys: list[str]) -> dict` (kỳ vọng cho prompt thật; `resolve_multi` nhân theo số mã)
  - `grade(expect: dict, flow: Flow, final_answer: str | None = None) -> dict` theo spec §7.4

- [ ] **Step 1: Viết `evals/scenarios.json`**

```json
[
  {
    "id": "open_bugs",
    "prompt": "backlog kiểm tra bugs open",
    "fixtures": {},
    "fakeState": "default",
    "match": {"keywords": [["bug", "bugs"], ["open", "mở"]], "issueKeys": "none"},
    "expect": {
      "calls": [{"tool": "get_my_open_bugs", "args": {}}],
      "order": "exact",
      "forbidden": ["get_issues", "get_issue", "get_bug_context", "get_my_project_status"],
      "finalAnswer": null
    },
    "nonMcp": null
  },
  {
    "id": "open_bugs_empty",
    "prompt": "backlog kiểm tra bugs open",
    "fixtures": {},
    "fakeState": "no_open_bugs",
    "match": null,
    "expect": {
      "calls": [{"tool": "get_my_open_bugs", "args": {}}],
      "order": "exact",
      "forbidden": ["get_issues", "get_issue", "get_bug_context", "get_my_project_status"],
      "finalAnswer": {"mustMention": ["0"]}
    },
    "nonMcp": null
  },
  {
    "id": "resolve_fixed",
    "prompt": "backlog resolve {issue}, bug này tôi fix rồi",
    "fixtures": {"issue": "OOP-90001"},
    "fakeState": "default",
    "match": {"keywords": [["resolve"]], "issueKeys": "one"},
    "expect": {
      "calls": [{"tool": "resolve_bug", "args": {"issue_key": "{issue}", "mode": "apply"}}],
      "order": "exact",
      "forbidden": ["get_bug_context", "get_issue", "get_bug_rules", "get_bug_fields"],
      "finalAnswer": null
    },
    "nonMcp": null
  },
  {
    "id": "resolve_multi",
    "prompt": "backlog resolve {a}, {b}, các bug này tôi fix rồi",
    "fixtures": {"a": "OOP-90001", "b": "OOP-90005"},
    "fakeState": "default",
    "match": {"keywords": [["resolve"]], "issueKeys": "many"},
    "expect": {
      "calls": [
        {"tool": "resolve_bug", "args": {"issue_key": "{a}", "mode": "apply"}},
        {"tool": "resolve_bug", "args": {"issue_key": "{b}", "mode": "apply"}}
      ],
      "order": "any",
      "forbidden": ["get_bug_context", "get_issue", "get_bug_rules", "get_bug_fields"],
      "finalAnswer": null
    },
    "nonMcp": null
  },
  {
    "id": "resolve_warning",
    "prompt": "backlog resolve {issue}, bug này tôi fix rồi",
    "fixtures": {"issue": "OOP-90003"},
    "fakeState": "default",
    "match": null,
    "expect": {
      "calls": [{"tool": "resolve_bug", "args": {"issue_key": "{issue}", "mode": "apply"}}],
      "order": "exact",
      "forbidden": ["get_bug_context", "get_issue", "get_bug_rules", "get_bug_fields"],
      "finalAnswer": {"mustMention": ["Tester"]}
    },
    "nonMcp": null
  },
  {
    "id": "fix_context",
    "prompt": "backlog fix {issue}",
    "fixtures": {"issue": "OOP-90002"},
    "fakeState": "default",
    "match": {"keywords": [["fix"]], "issueKeys": "one"},
    "expect": {
      "calls": [{"tool": "get_bug_context", "args": {"issue_key": "{issue}"}}],
      "order": "exact",
      "forbidden": ["get_issue"],
      "finalAnswer": null
    },
    "nonMcp": null
  },
  {
    "id": "fix_context_attachment",
    "prompt": "backlog fix {issue}",
    "fixtures": {"issue": "OOP-90004"},
    "fakeState": "default",
    "match": null,
    "expect": {
      "calls": [{"tool": "get_bug_context", "args": {"issue_key": "{issue}"}}],
      "order": "exact",
      "forbidden": ["get_issue"],
      "finalAnswer": {"mustMention": ["login-error.png"]}
    },
    "nonMcp": null
  }
]
```

- [ ] **Step 2: Viết test fail** — `tests/test_telemetry_grader.py`:

```python
from backlog_tool.telemetry_grader import expect_for, grade, load_scenarios, match_prompt, render_scenario
from backlog_tool.telemetry_store import Call, Flow


def call(tool, args, status="ok", errors=None):
    return Call(
        trace_id=f"{tool}{sorted(args.items())}", ts="2026-09-24T10:00:00.000+07:00", tool=tool,
        arguments=args, status=status, duration_ms=1, api_calls=1, response_bytes=100, est_tokens=25,
        client="c", session_id="s", surface="mcp", run_id="r", scenario=None,
        issue_key=args.get("issue_key"), project_key="OOP", errors=errors or [],
    )


def scenario(scenario_id):
    return render_scenario(next(s for s in load_scenarios() if s["id"] == scenario_id))


def test_all_scenarios_render_without_placeholders():
    for s in load_scenarios():
        rendered = render_scenario(s)
        assert "{" not in rendered["prompt"]
        for expected in rendered["expect"]["calls"]:
            assert all("{" not in str(v) for v in expected["args"].values())


def test_resolve_fast_path_passes_and_preview_is_extra():
    expect = scenario("resolve_fixed")["expect"]
    good = grade(expect, Flow("r", [call("resolve_bug", {"issue_key": "OOP-90001", "mode": "apply"})]))
    assert good["pass"] is True and good["extraCalls"] == []

    two = grade(expect, Flow("r", [
        call("resolve_bug", {"issue_key": "OOP-90001", "mode": "preview"}),
        call("resolve_bug", {"issue_key": "OOP-90001", "mode": "apply"}),
    ]))
    assert two["pass"] is False and two["extraCalls"] == ["resolve_bug"]


def test_forbidden_and_arg_errors_fail():
    expect = scenario("resolve_fixed")["expect"]
    result = grade(expect, Flow("r", [
        call("get_bug_context", {"issue_key": "OOP-90001"}),
        call("resolve_bug", {"issueKey": "OOP-90001"}, status="invalid_arguments", errors=[{"kind": "arg_error", "unknown": ["issueKey"]}]),
        call("resolve_bug", {"issue_key": "OOP-90001", "mode": "apply"}),
    ]))
    assert result["pass"] is False
    assert result["forbiddenHits"] == ["get_bug_context"]
    assert result["argErrors"] == [{"tool": "resolve_bug", "unknown": ["issueKey"]}]


def test_multi_any_order_and_final_answer():
    expect = scenario("resolve_multi")["expect"]
    flow = Flow("r", [
        call("resolve_bug", {"issue_key": "OOP-90005", "mode": "apply"}),
        call("resolve_bug", {"issue_key": "OOP-90001", "mode": "apply"}),
    ])
    assert grade(expect, flow)["pass"] is True

    warn = scenario("resolve_warning")["expect"]
    flow = Flow("r", [call("resolve_bug", {"issue_key": "OOP-90003", "mode": "apply"})])
    assert grade(warn, flow, final_answer="Đã resolve. Cảnh báo: Detected Role không phải Tester")["pass"] is True
    missing = grade(warn, flow, final_answer="Đã resolve.")
    assert missing["pass"] is False and missing["finalAnswerCheck"] == {"missing": ["Tester"]}
    assert grade(warn, flow, final_answer=None)["finalAnswerCheck"] == {"skipped": "no final answer"}


def test_match_prompt_for_real_usage():
    scenarios = load_scenarios()
    assert match_prompt("dùng backlog mcp resolve OOP-12762, bug này tôi fix rồi", scenarios)[0]["id"] == "resolve_fixed"
    matched, keys = match_prompt("backlog resolve OOP-1, OOP-2 fix rồi", scenarios)
    assert matched["id"] == "resolve_multi" and keys == ["OOP-1", "OOP-2"]
    assert match_prompt("backlog fix NLN-12345", scenarios)[0]["id"] == "fix_context"
    assert match_prompt("Backlog kiểm tra bugs open", scenarios)[0]["id"] == "open_bugs"
    assert match_prompt("resolve OOP-1", scenarios) is None
    assert match_prompt("backlog status tuần này", scenarios) is None

    expect = expect_for(matched, keys)
    assert [c["args"]["issue_key"] for c in expect["calls"]] == ["OOP-1", "OOP-2"]
```

- [ ] **Step 3: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError: backlog_tool.telemetry_grader`.

- [ ] **Step 4: Viết `backlog_tool/telemetry_grader.py`**

```python
"""Tier-3: scenario definitions, real-prompt matching, and grading a flow against expectations."""

import copy
import json
import os
import re

from . import settings

SCENARIOS_PATH = os.path.join(settings.MCP_ROOT, "evals", "scenarios.json")
ISSUE_KEY_IN_TEXT = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")


def load_scenarios(path=None):
    with open(path or SCENARIOS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _fill(value, fixtures):
    if isinstance(value, str):
        for name, fixture in fixtures.items():
            value = value.replace("{" + name + "}", fixture)
        return value
    if isinstance(value, dict):
        return {k: _fill(v, fixtures) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, fixtures) for v in value]
    return value


def render_scenario(scenario):
    rendered = copy.deepcopy(scenario)
    fixtures = scenario.get("fixtures") or {}
    rendered["prompt"] = _fill(scenario["prompt"], fixtures)
    rendered["expect"] = _fill(scenario["expect"], fixtures)
    return rendered


def match_prompt(prompt, scenarios):
    text = (prompt or "").lower()
    if "backlog" not in text:
        return None
    keys = ISSUE_KEY_IN_TEXT.findall(prompt)
    count = "none" if not keys else ("one" if len(keys) == 1 else "many")
    for scenario in scenarios:
        rule = scenario.get("match")
        if not rule or rule.get("issueKeys") != count:
            continue
        if all(any(word in text for word in group) for group in rule.get("keywords", [])):
            return scenario, keys
    return None


def expect_for(scenario, issue_keys):
    expect = copy.deepcopy(scenario["expect"])
    template = expect["calls"][0]
    if scenario.get("match", {}).get("issueKeys") == "many":
        expect["calls"] = [
            {"tool": template["tool"], "args": {**template["args"], "issue_key": key}} for key in issue_keys
        ]
    elif issue_keys:
        fixtures = {name: issue_keys[0] for name in (scenario.get("fixtures") or {})}
        expect = _fill(expect, fixtures)
    return expect


def _matches(expected, call):
    return expected["tool"] == call.tool and all(call.arguments.get(k) == v for k, v in expected["args"].items())


def grade(expect, flow, final_answer=None):
    calls = [c for c in flow.calls if c.status not in ("invalid_arguments", "rejected")]
    reasons = []

    remaining = list(calls)
    matched = []
    for expected in expect["calls"]:
        index = next((i for i, c in enumerate(remaining) if _matches(expected, c)), None)
        if index is None:
            reasons.append(f"missing expected call {expected['tool']} {expected['args']}")
            continue
        matched.append(remaining.pop(index))
    extra = [c.tool for c in remaining]
    if extra:
        reasons.append(f"extra calls: {extra}")
    if expect.get("order") == "exact" and not extra and matched and [c.trace_id for c in matched] != [c.trace_id for c in calls]:
        reasons.append("calls not in expected order")

    forbidden = [c.tool for c in flow.calls if c.tool in expect.get("forbidden", [])]
    if forbidden:
        reasons.append(f"forbidden calls: {forbidden}")

    arg_errors = [
        {"tool": c.tool, "unknown": e.get("unknown", [])}
        for c in flow.calls for e in c.errors if e.get("kind") == "arg_error"
    ]
    if arg_errors:
        reasons.append(f"argument errors: {arg_errors}")

    final_check = None
    rule = expect.get("finalAnswer")
    if rule:
        if final_answer is None:
            final_check = {"skipped": "no final answer"}
        else:
            missing = [word for word in rule["mustMention"] if word.lower() not in final_answer.lower()]
            final_check = {"missing": missing} if missing else {"ok": True}
            if missing:
                reasons.append(f"final answer does not mention {missing}")

    return {
        "pass": not reasons,
        "reasons": reasons,
        "mcpCalls": [{"tool": c.tool, "arguments": c.arguments, "status": c.status} for c in flow.calls],
        "extraCalls": extra,
        "forbiddenHits": forbidden,
        "argErrors": arg_errors,
        "finalAnswerCheck": final_check,
        "estTokens": sum(c.est_tokens for c in flow.calls),
    }
```

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_telemetry_grader.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add evals/__init__.py evals/scenarios.json backlog_tool/telemetry_grader.py tests/test_telemetry_grader.py
git commit -m "Add eval scenarios and scenario grader

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 10: Phát hiện field thiếu

**Files:**
- Create: `backlog_tool/telemetry_missing.py`
- Modify: `backlog_tool/telemetry_rules.py` (thêm finding `missing_field` / `routing`)
- Test: `tests/test_telemetry_missing.py`

**Interfaces:**
- Consumes: `Flow`, `Call` (Task 7), `SPECIALIZED` (Task 8).
- Produces: `find_missing_fields(flow: Flow, final_answer: str | None = None) -> list[dict]` với mỗi phần tử `{"after": <tool A>, "followUp": <tool B>, "confirmed": [path..], "candidates": [path..], "verdict": "missing_field"|"routing", "traceIds": [A, B]}`. `apply_rules(flow, final_answer=None)` nhận thêm tham số và thêm finding code `missing_field` (severity `warning`) hoặc `routing` (severity `candidate`).

- [ ] **Step 1: Viết test fail** — `tests/test_telemetry_missing.py`:

```python
from backlog_tool.telemetry_missing import find_missing_fields
from backlog_tool.telemetry_rules import apply_rules
from backlog_tool.telemetry_store import Call, Flow


def call(tool, args, result, trace):
    return Call(
        trace_id=trace, ts="2026-09-24T10:00:00.000+07:00", tool=tool, arguments=args, status="ok",
        duration_ms=1, api_calls=1, response_bytes=100, est_tokens=25, client="c", session_id="s",
        surface="mcp", run_id=None, scenario=None, issue_key="OOP-1", project_key="OOP", result=result,
    )


CONTEXT = {"ok": True, "data": {"issueKey": "OOP-1", "summary": "Login fails"}}
ISSUE = {"ok": True, "data": {"issueKey": "OOP-1", "summary": "Login fails", "priority": "High", "category": ["Auth module"]}}


def test_confirmed_missing_field_when_value_is_used_later():
    flow = Flow("f", [
        call("get_bug_context", {"issue_key": "OOP-1"}, CONTEXT, "a"),
        call("get_issue", {"issue_ref": "OOP-1"}, ISSUE, "b"),
    ])
    [item] = find_missing_fields(flow, final_answer="Bug thuộc Auth module, ưu tiên cao")
    assert item["verdict"] == "missing_field"
    assert item["confirmed"] == ["data.category[]"]
    assert sorted(item["candidates"]) == ["data.category[]", "data.priority"]
    assert "missing_field" in [f["code"] for f in apply_rules(flow, final_answer="Auth module")]


def test_routing_when_nothing_from_follow_up_is_used():
    flow = Flow("f", [
        call("get_bug_context", {"issue_key": "OOP-1"}, CONTEXT, "a"),
        call("get_issue", {"issue_ref": "OOP-1"}, ISSUE, "b"),
    ])
    [item] = find_missing_fields(flow, final_answer="Đã xem bug.")
    assert item["verdict"] == "routing" and item["confirmed"] == []


def test_value_used_in_later_call_arguments_confirms():
    flow = Flow("f", [
        call("get_bug_context", {"issue_key": "OOP-1"}, CONTEXT, "a"),
        call("get_issue", {"issue_ref": "OOP-1"}, ISSUE, "b"),
        call("update_issue", {"issue_ref": "OOP-1", "category": "Auth module"}, {"ok": True}, "c"),
    ])
    assert find_missing_fields(flow)[0]["confirmed"] == ["data.category[]"]


def test_no_follow_up_no_result():
    flow = Flow("f", [call("get_bug_context", {"issue_key": "OOP-1"}, CONTEXT, "a")])
    assert find_missing_fields(flow) == []
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError`.

- [ ] **Step 3: Viết `backlog_tool/telemetry_missing.py`**

```python
"""Detect fields a specialized tool did not return but the model fetched with a follow-up call and then used."""

import json

from .telemetry_rules import SPECIALIZED

MIN_TEXT_LENGTH = 4


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for child in value:
            yield from _leaves(child, f"{prefix}[]")
    else:
        yield prefix, value


def _paths(value):
    return {path for path, _ in _leaves(value)}


def _used(value, haystack):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return str(value) in haystack
    text = str(value)
    return len(text) >= MIN_TEXT_LENGTH and text.lower() in haystack.lower()


def find_missing_fields(flow, final_answer=None):
    specialized_for = {generic: special for generic, special in SPECIALIZED}
    findings = []
    calls = flow.calls
    for i, follow_up in enumerate(calls):
        special = specialized_for.get(follow_up.tool)
        if not special:
            continue
        earlier = [c for c in calls[:i] if c.tool == special and c.issue_key == follow_up.issue_key]
        if not earlier or follow_up.result is None:
            continue
        first = earlier[-1]
        candidates = sorted(_paths(follow_up.result) - _paths(first.result))
        haystack = " ".join(
            [json.dumps(c.arguments, ensure_ascii=False) for c in calls[i + 1:]] + [final_answer or ""]
        )
        values = {}
        for path, value in _leaves(follow_up.result):
            if path in candidates:
                values.setdefault(path, []).append(value)
        confirmed = sorted(path for path, items in values.items() if any(_used(v, haystack) for v in items))
        findings.append({
            "after": first.tool,
            "followUp": follow_up.tool,
            "confirmed": confirmed,
            "candidates": candidates,
            "verdict": "missing_field" if confirmed else "routing",
            "traceIds": [first.trace_id, follow_up.trace_id],
        })
    return findings
```

- [ ] **Step 4: Nối vào rule** — trong `backlog_tool/telemetry_rules.py`: đổi chữ ký `def apply_rules(flow):` thành `def apply_rules(flow, final_answer=None):`; trước `return findings` thêm:

```python
    from .telemetry_missing import find_missing_fields

    for item in find_missing_fields(flow, final_answer):
        if item["verdict"] == "missing_field":
            reason = f"{item['followUp']} after {item['after']} supplied fields that were then used: {item['confirmed']}"
            severity = "warning"
        else:
            reason = f"{item['followUp']} after {item['after']} but none of its extra fields were used (routing/wording)."
            severity = "candidate"
        findings.append({"code": item["verdict"], "severity": severity, "reason": reason, "traceIds": item["traceIds"]})
```

  (Import nằm trong hàm để tránh vòng import `telemetry_missing` ↔ `telemetry_rules`.) Trong `tests/test_telemetry_rules.py`, test `test_duplicate_and_generic_after_specialized` giờ có thêm code `routing` (result `None` → không có finding; `Call` trong test đó không có `result` nên `find_missing_fields` bỏ qua) — chạy và xác nhận vẫn PASS.

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_telemetry_missing.py tests/test_telemetry_rules.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backlog_tool/telemetry_missing.py backlog_tool/telemetry_rules.py tests/test_telemetry_missing.py
git commit -m "Detect missing fields behind follow-up generic calls

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 11: Đọc transcript Claude Code

**Files:**
- Create: `backlog_tool/claude_transcripts.py`
- Create: `tests/fixtures/claude_transcript_sample.jsonl`
- Test: `tests/test_claude_transcripts.py`

**Interfaces:**
- Consumes: `Flow`, `Call`, `load_calls` (Task 7).
- Produces:
  - `@dataclass PromptTurn(prompt, ts, model, tool_uses: list[dict], final_answer, project_dir, session_file)`; mỗi `tool_uses` phần tử `{"name", "input", "ts", "is_error"}`.
  - `read_prompt_turns(path) -> list[PromptTurn]`
  - `find_transcripts(since: str | None = None, root=None) -> list[str]` (mặc định `~/.claude/projects/*/*.jsonl`, lọc theo mtime ≥ since)
  - `turn_to_flow(turn: PromptTurn, calls: list[Call]) -> Flow` (gán `Call` khớp tool + arguments + thời gian ±5 s; MCP tool không có trong telemetry vẫn vào flow dưới dạng `Call` tối thiểu với `trace_id="transcript:<i>"`)

- [ ] **Step 1: Tạo fixture transcript** — `tests/fixtures/claude_transcript_sample.jsonl` (mỗi dòng một JSON; mô phỏng đúng định dạng Claude Code: tin nhắn `user` có `message.content` là chuỗi hoặc list, `assistant` có `message.model` và `content[]` chứa `text`/`tool_use`, `user` chứa `tool_result`):

```jsonl
{"type":"user","timestamp":"2026-09-23T10:20:00.000Z","cwd":"/home/u/proj","message":{"role":"user","content":"<command-name>/clear</command-name>"}}
{"type":"user","timestamp":"2026-09-23T10:20:01.000Z","isMeta":true,"message":{"role":"user","content":"Caveat: meta"}}
{"type":"user","timestamp":"2026-09-23T10:20:02.000Z","cwd":"/home/u/proj","message":{"role":"user","content":[{"type":"text","text":"<system-reminder>ctx</system-reminder>"},{"type":"text","text":"backlog resolve OOP-12781, bug này tôi fix rồi"}]}}
{"type":"user","timestamp":"2026-09-23T10:20:03.000Z","message":{"role":"user","content":[{"type":"text","text":"Base directory for this skill: /home/u/.claude/plugins/x\n# Skill"}]}}
{"type":"user","timestamp":"2026-09-23T10:20:04.000Z","message":{"role":"user","content":"<local-command-caveat>Caveat: generated</local-command-caveat>"}}
{"type":"assistant","timestamp":"2026-09-23T10:20:05.000Z","message":{"model":"claude-opus-5-5","content":[{"type":"text","text":"Resolving."},{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"git log -1"}}]}}
{"type":"user","timestamp":"2026-09-23T10:20:06.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"abc fix","is_error":false}]}}
{"type":"assistant","timestamp":"2026-09-23T10:20:08.000Z","message":{"model":"claude-opus-5-5","content":[{"type":"tool_use","id":"t2","name":"mcp__backlog__resolve_bug","input":{"issue_key":"OOP-12781","mode":"apply"}}]}}
{"type":"user","timestamp":"2026-09-23T10:20:10.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t2","content":[{"type":"text","text":"{}"}],"is_error":false}]}}
{"type":"assistant","timestamp":"2026-09-23T10:20:12.000Z","message":{"model":"claude-opus-5-5","content":[{"type":"text","text":"Đã resolve OOP-12781."}]}}
{"type":"user","timestamp":"2026-09-23T10:25:00.000Z","message":{"role":"user","content":"cảm ơn"}}
{"type":"user","timestamp":"2026-09-23T10:30:00.000Z","message":{"role":"user","content":"OOP-12777 tôi fix rồi"}}
{"type":"assistant","timestamp":"2026-09-23T10:30:05.000Z","message":{"model":"claude-opus-5-5","content":[{"type":"tool_use","id":"t3","name":"mcp__backlog__resolve_bug","input":{"issue_key":"OOP-12777","mode":"apply"}}]}}
{"type":"user","timestamp":"2026-09-23T10:30:07.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t3","content":"{}","is_error":false}]}}
```

- [ ] **Step 2: Viết test fail** — `tests/test_claude_transcripts.py`:

```python
import os

from backlog_tool import telemetry
from backlog_tool.claude_transcripts import read_prompt_turns, turn_to_flow
from backlog_tool.telemetry_store import Call

SAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "claude_transcript_sample.jsonl")


def test_only_real_prompts_are_turns():
    turns = read_prompt_turns(SAMPLE)
    assert [t.prompt for t in turns] == ["backlog resolve OOP-12781, bug này tôi fix rồi", "cảm ơn", "OOP-12777 tôi fix rồi"]
    first = turns[0]
    assert first.model == "claude-opus-5-5"
    assert [u["name"] for u in first.tool_uses] == ["Bash", "mcp__backlog__resolve_bug"]
    assert first.final_answer == "Đã resolve OOP-12781."
    assert first.project_dir == "/home/u/proj"


def test_turn_to_flow_matches_telemetry_call_and_keeps_non_mcp():
    turn = read_prompt_turns(SAMPLE)[0]
    matching = Call(
        trace_id="real", ts="2026-09-23T17:20:09.000+07:00", tool="resolve_bug",
        arguments={"issue_key": "OOP-12781", "mode": "apply"}, status="ok", duration_ms=1500, api_calls=2,
        response_bytes=800, est_tokens=200, client="claude-code", session_id="s", surface="mcp", run_id=None,
        scenario=None, issue_key="OOP-12781", project_key="OOP", result={"ok": True},
    )
    flow = turn_to_flow(turn, [matching])
    assert [c.trace_id for c in flow.calls] == ["real"]
    assert flow.non_mcp == [{"name": "Bash", "input": {"command": "git log -1"}}]
    assert flow.prompt == turn.prompt and flow.final_answer == "Đã resolve OOP-12781."
    assert flow.model == "claude-opus-5-5"


def test_follow_up_prompt_without_backlog_word_keeps_its_tool_calls():
    turn = read_prompt_turns(SAMPLE)[2]
    assert [u["name"] for u in turn.tool_uses] == ["mcp__backlog__resolve_bug"]


def test_turn_to_flow_without_telemetry_uses_transcript_call():
    turn = read_prompt_turns(SAMPLE)[0]
    flow = turn_to_flow(turn, [])
    assert [c.tool for c in flow.calls] == ["resolve_bug"]
    assert flow.calls[0].trace_id.startswith("transcript:")
```

- [ ] **Step 3: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError`.

- [ ] **Step 4: Viết `backlog_tool/claude_transcripts.py`**

```python
"""Read Claude Code transcripts (~/.claude/projects/*/*.jsonl) into prompt turns and flows."""

import glob
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from .telemetry_store import Call, Flow

MCP_PREFIX = "mcp__backlog__"
MATCH_WINDOW_SECONDS = 5
_WRAPPED = re.compile(
    r"^\s*(<(system-reminder|command-name|command-message|command-args|local-command-stdout|local-command-caveat)\b"
    r"|Base directory for this skill:|\[Request interrupted|Caveat: )"
)


@dataclass
class PromptTurn:
    prompt: str
    ts: str
    model: str | None = None
    tool_uses: list = field(default_factory=list)
    final_answer: str | None = None
    project_dir: str | None = None
    session_file: str | None = None


def _prompt_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return None if _WRAPPED.match(content) else content.strip()
    if isinstance(content, list):
        if any(part.get("type") == "tool_result" for part in content if isinstance(part, dict)):
            return None
        texts = [
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and not _WRAPPED.match(part.get("text", ""))
        ]
        texts = [text for text in texts if text]
        return "\n".join(texts) or None
    return None


def read_prompt_turns(path):
    turns = []
    current = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") or {}
            if entry.get("type") == "user" and not entry.get("isMeta"):
                prompt = _prompt_text(message)
                if prompt:
                    current = PromptTurn(prompt, entry.get("timestamp", ""), project_dir=entry.get("cwd"), session_file=path)
                    turns.append(current)
                    continue
                for part in message.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "tool_result" and current:
                        for use in current.tool_uses:
                            if use.get("id") == part.get("tool_use_id"):
                                use["is_error"] = bool(part.get("is_error"))
            elif entry.get("type") == "assistant" and current:
                current.model = message.get("model") or current.model
                for part in message.get("content") or []:
                    if part.get("type") == "tool_use":
                        current.tool_uses.append({
                            "id": part.get("id"), "name": part.get("name"), "input": part.get("input") or {},
                            "ts": entry.get("timestamp", ""), "is_error": False,
                        })
                    elif part.get("type") == "text" and part.get("text", "").strip():
                        current.final_answer = part["text"].strip()
    return turns


def find_transcripts(since=None, root=None):
    root = root or os.path.expanduser("~/.claude/projects")
    paths = glob.glob(os.path.join(root, "*", "*.jsonl"))
    if since:
        cutoff = datetime.fromisoformat(since[:10]).timestamp()
        paths = [p for p in paths if os.path.getmtime(p) >= cutoff]
    return sorted(paths)


def _epoch(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def turn_to_flow(turn, calls):
    flow = Flow(f"prompt-{turn.ts}", [], prompt=turn.prompt, final_answer=turn.final_answer, model=turn.model, client="claude-code")
    used = set()
    for index, use in enumerate(turn.tool_uses):
        name = use["name"] or ""
        if not name.startswith(MCP_PREFIX):
            flow.non_mcp.append({"name": name, "input": use["input"]})
            continue
        tool = name[len(MCP_PREFIX):]
        use_time = _epoch(use["ts"])
        match = next((
            call for call in calls
            if call.trace_id not in used and call.tool == tool and call.arguments == use["input"]
            and use_time is not None and _epoch(call.ts) is not None
            and abs(_epoch(call.ts) - use_time) <= MATCH_WINDOW_SECONDS
        ), None)
        if match is None:
            match = Call(
                trace_id=f"transcript:{index}", ts=use["ts"], tool=tool, arguments=use["input"],
                status="error" if use.get("is_error") else "ok", duration_ms=0, api_calls=0,
                response_bytes=0, est_tokens=0, client="claude-code", session_id="", surface="mcp",
                run_id=None, scenario=None, issue_key=use["input"].get("issue_key"), project_key=None,
            )
        used.add(match.trace_id)
        flow.calls.append(match)
    return flow
```

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_claude_transcripts.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backlog_tool/claude_transcripts.py tests/fixtures/claude_transcript_sample.jsonl tests/test_claude_transcripts.py
git commit -m "Read Claude Code transcripts into prompt flows

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 12: Báo cáo và CLI `telemetry`

**Files:**
- Create: `backlog_tool/telemetry_report.py`
- Modify: `backlog_tool/cli.py` (parser + `run_handler`)
- Test: `tests/test_telemetry_report.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 7–11.
- Produces:
  - `parse_since(value: str | None) -> str | None` (`"1d"`, `"7d"`, `"12h"` → ISO; ISO date/datetime giữ nguyên)
  - `flow_summary(flow: Flow, scenarios) -> dict` (`{flowId, startedAt, prompt, model, client, tools, nonMcp, findings, grade}`; `grade` chỉ có khi flow khớp kịch bản: theo `scenario` của call (eval) hoặc `match_prompt(flow.prompt)` (dùng thật))
  - `build_report(flows: list[Flow], scenarios) -> dict` (`{flows, totals: {flows, calls, estTokens}, topTools, recurringErrors, byClient, passRate}`)
  - `report_from_logs(since=None, run_id=None, log_dir=None) -> dict`
  - `report_from_claude(since=None, root=None, log_dir=None) -> dict`
  - CLI: `backlog-cli telemetry report [--since] [--run] [--json]`, `backlog-cli telemetry import-claude [--since] [--root] [--json]`; không `--json` → in bảng Markdown ngắn.

- [ ] **Step 1: Viết test fail** — `tests/test_telemetry_report.py`:

```python
from backlog_tool import telemetry
from backlog_tool.telemetry_grader import load_scenarios
from backlog_tool.telemetry_report import build_report, parse_since, report_from_logs
from backlog_tool.telemetry_store import group_flows, load_calls


def make(tool, args, status="ok", size=400):
    telemetry.start_call(tool, args)
    telemetry.finish_call(status, result={"ok": True}, text="t", response_bytes=size, error="boom" if status != "ok" else None)


def test_parse_since():
    assert parse_since(None) is None
    assert parse_since("2026-09-24") == "2026-09-24"
    assert len(parse_since("1d")) >= 19


def test_report_from_logs_with_eval_grade_and_rules():
    telemetry.set_eval_tags("run-1", "resolve_fixed")
    make("get_bug_context", {"issue_key": "OOP-90001"})
    make("resolve_bug", {"issue_key": "OOP-90001", "mode": "apply"})
    telemetry.set_eval_tags(None, None)
    make("get_issue", {"issue_ref": "OOP-5"}, status="error", size=9000)

    report = report_from_logs()
    [eval_flow] = [f for f in report["flows"] if f["flowId"] == "run-1"]
    assert eval_flow["grade"]["pass"] is False
    assert eval_flow["grade"]["forbiddenHits"] == ["get_bug_context"]
    assert report["passRate"] == {"resolve_fixed": {"pass": 0, "runs": 1}}
    assert report["topTools"][0]["tool"] == "get_issue"
    assert report["recurringErrors"][0] == {"kind": "tool_error", "tool": "get_issue", "detail": "boom", "count": 1}
    assert report["totals"]["calls"] == 3


def test_build_report_real_usage_uses_prompt_match():
    make("resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    [flow] = group_flows(load_calls())
    flow.prompt = "backlog resolve OOP-1, bug này tôi fix rồi"
    report = build_report([flow], load_scenarios())
    assert report["flows"][0]["grade"]["pass"] is True
```

Thêm vào `tests/test_cli.py` (class `ParserTest`):

```python
    def test_telemetry_commands_parse(self):
        args = self.parser.parse_args(["telemetry", "report", "--since", "1d", "--run", "r1"])
        self.assertEqual(("telemetry", "report", "1d", "r1"), (args.group, args.action, args.since, args.run))
        args = self.parser.parse_args(["telemetry", "import-claude"])
        self.assertEqual(("telemetry", "import-claude"), (args.group, args.action))
        self.assertIsNone(cli.is_dry_run(args))
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError: backlog_tool.telemetry_report`.

- [ ] **Step 3: Viết `backlog_tool/telemetry_report.py`**

```python
"""Build readable reports from telemetry flows (tier 1 aggregates + tier 2 rules + tier 3 grades)."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .claude_transcripts import find_transcripts, read_prompt_turns, turn_to_flow
from .telemetry_grader import expect_for, grade, load_scenarios, match_prompt, render_scenario
from .telemetry_rules import apply_rules
from .telemetry_store import group_flows, load_calls

_RELATIVE = re.compile(r"^(\d+)([dh])$")


def parse_since(value):
    if not value:
        return None
    match = _RELATIVE.match(value)
    if not match:
        return value
    amount, unit = int(match.group(1)), match.group(2)
    delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
    return (datetime.now().astimezone() - delta).isoformat(timespec="seconds")


def _grade_for(flow, scenarios):
    scenario_id = next((c.scenario for c in flow.calls if c.scenario), None)
    if scenario_id:
        scenario = next((s for s in scenarios if s["id"] == scenario_id), None)
        if scenario:
            return scenario_id, grade(render_scenario(scenario)["expect"], flow, flow.final_answer)
    if flow.prompt:
        matched = match_prompt(flow.prompt, scenarios)
        if matched:
            scenario, keys = matched
            return scenario["id"], grade(expect_for(scenario, keys), flow, flow.final_answer)
    return None, None


def flow_summary(flow, scenarios):
    scenario_id, result = _grade_for(flow, scenarios)
    summary = {
        "flowId": flow.flow_id,
        "startedAt": flow.started_at,
        "prompt": flow.prompt,
        "model": flow.model,
        "client": flow.client,
        "tools": flow.tools,
        "nonMcp": [item["name"] for item in flow.non_mcp],
        "estTokens": sum(c.est_tokens for c in flow.calls),
        "durationMs": round(sum(c.duration_ms for c in flow.calls), 1),
        "findings": apply_rules(flow, flow.final_answer),
    }
    if result is not None:
        summary["scenario"] = scenario_id
        summary["grade"] = result
    return summary


def build_report(flows, scenarios):
    summaries = [flow_summary(flow, scenarios) for flow in flows]
    calls = [call for flow in flows for call in flow.calls]

    by_tool = defaultdict(lambda: {"calls": 0, "estTokens": 0, "durationMs": 0.0, "errors": 0})
    for call in calls:
        row = by_tool[call.tool]
        row["calls"] += 1
        row["estTokens"] += call.est_tokens
        row["durationMs"] += call.duration_ms
        row["errors"] += int(call.status != "ok")
    top_tools = sorted(
        ({"tool": tool, **row, "durationMs": round(row["durationMs"], 1)} for tool, row in by_tool.items()),
        key=lambda row: -row["estTokens"],
    )

    errors = Counter()
    for call in calls:
        for error in call.errors:
            detail = ",".join(error.get("unknown") or []) if error.get("kind") == "arg_error" else error.get("message", "")
            errors[(error.get("kind"), call.tool, detail)] += 1
    recurring = [
        {"kind": kind, "tool": tool, "detail": detail, "count": count}
        for (kind, tool, detail), count in errors.most_common()
    ]

    by_client = defaultdict(lambda: {"flows": 0, "calls": 0, "estTokens": 0})
    for flow in flows:
        key = flow.model or flow.client or "unknown"
        by_client[key]["flows"] += 1
        by_client[key]["calls"] += len(flow.calls)
        by_client[key]["estTokens"] += sum(c.est_tokens for c in flow.calls)

    pass_rate = defaultdict(lambda: {"pass": 0, "runs": 0})
    for summary in summaries:
        if "grade" in summary:
            pass_rate[summary["scenario"]]["runs"] += 1
            pass_rate[summary["scenario"]]["pass"] += int(summary["grade"]["pass"])

    return {
        "flows": summaries,
        "totals": {"flows": len(flows), "calls": len(calls), "estTokens": sum(c.est_tokens for c in calls)},
        "topTools": top_tools,
        "recurringErrors": recurring,
        "byClient": dict(by_client),
        "passRate": dict(pass_rate),
    }


def report_from_logs(since=None, run_id=None, log_dir=None):
    flows = group_flows(load_calls(log_dir=log_dir, since=parse_since(since), run_id=run_id))
    return build_report(flows, load_scenarios())


def report_from_claude(since=None, root=None, log_dir=None):
    since_iso = parse_since(since)
    calls = load_calls(log_dir=log_dir, since=since_iso)
    flows = []
    for path in find_transcripts(since_iso, root):
        for turn in read_prompt_turns(path):
            if since_iso and turn.ts[:19] < since_iso[:19]:
                continue
            uses_backlog = any((u["name"] or "").startswith("mcp__backlog__") for u in turn.tool_uses)
            if "backlog" not in turn.prompt.lower() and not uses_backlog:
                continue
            flows.append(turn_to_flow(turn, calls))
    return build_report(flows, load_scenarios())


def to_markdown(report):
    lines = [f"Flows: {report['totals']['flows']} · calls: {report['totals']['calls']} · estTokens: {report['totals']['estTokens']}", ""]
    if report["passRate"]:
        lines += ["| Scenario | Pass/Runs |", "|---|---|"]
        lines += [f"| {k} | {v['pass']}/{v['runs']} |" for k, v in sorted(report["passRate"].items())]
        lines.append("")
    lines += ["| Tool | Calls | estTokens | ms | Errors |", "|---|---|---|---|---|"]
    lines += [f"| {r['tool']} | {r['calls']} | {r['estTokens']} | {r['durationMs']} | {r['errors']} |" for r in report["topTools"]]
    if report["recurringErrors"]:
        lines += ["", "| Error | Tool | Detail | Count |", "|---|---|---|---|"]
        lines += [f"| {e['kind']} | {e['tool']} | {e['detail'][:60]} | {e['count']} |" for e in report["recurringErrors"][:15]]
    lines += ["", "| Flow | Tools | Findings | Grade |", "|---|---|---|---|"]
    for flow in report["flows"]:
        grade_text = "" if "grade" not in flow else ("PASS" if flow["grade"]["pass"] else "FAIL: " + "; ".join(flow["grade"]["reasons"])[:80])
        findings = ",".join(sorted({f["code"] for f in flow["findings"]}))
        lines.append(f"| {flow['flowId'][:24]} | {' → '.join(flow['tools'])} | {findings} | {grade_text} |")
    return "\n".join(lines)
```

- [ ] **Step 4: CLI** — trong `backlog_tool/cli.py` `build_parser()` sau block `story`:

```python
    telemetry_group = groups.add_parser("telemetry", help="Local telemetry analysis").add_subparsers(dest="action", required=True)
    g = telemetry_group.add_parser("report", help="Flows, rule findings and scenario grades from logs/")
    g.add_argument("--since", help="1d, 12h, or ISO date/datetime")
    g.add_argument("--run", help="Only one eval runId")
    g.add_argument("--json", action="store_true", dest="as_json")
    g = telemetry_group.add_parser("import-claude", help="Grade Claude Code transcripts that mention backlog")
    g.add_argument("--since", help="1d, 12h, or ISO date/datetime")
    g.add_argument("--root", help="Transcript root (default ~/.claude/projects)")
    g.add_argument("--json", action="store_true", dest="as_json")
```

  Trong `run_handler`, trước nhánh cuối:

```python
    if group == "telemetry":
        if action == "report":
            return report_from_logs(since=args.since, run_id=args.run)
        return report_from_claude(since=args.since, root=args.root)
```

  Import: `from backlog_tool.telemetry_report import report_from_claude, report_from_logs, to_markdown`. Trong `execute`, ngay sau `presented_data = present(...)`, nếu `args.group == "telemetry"` thì `text = json.dumps(presented_data, indent=2, ensure_ascii=False) if args.as_json else to_markdown(presented_data)` và bỏ qua nhánh `--table`/`json.dumps` mặc định (đặt khối `if args.group == "telemetry": … else: <khối cũ>`). Thêm `"telemetry:report"` và `"telemetry:import-claude"` **không** vào `CLI_TOOL_NAMES` (log dưới tên lệnh).

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_telemetry_report.py tests/test_cli.py -q` → PASS.

- [ ] **Step 6: Chạy thật** — `uv run backlog-cli telemetry import-claude --since 2026-09-22` → in bảng. Kỳ vọng: có flow cho mọi prompt ngày 23/09 đã gọi tool backlog, kể cả prompt không chứa chữ "backlog" (ví dụ "OOP-12777 tôi fix rồi"); prompt có "backlog" + "resolve" được chấm theo `resolve_fixed`; prompt không khớp kịch bản vẫn có findings tầng 2. Ghi lại số flow vào tin nhắn commit.

- [ ] **Step 7: Commit**

```bash
git add backlog_tool/telemetry_report.py backlog_tool/cli.py tests/test_telemetry_report.py tests/test_cli.py
git commit -m "Add telemetry report and Claude transcript import commands

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 13: Fixture log ngày 23/09 và kiểm chứng tầng phân tích (đóng P2)

**Files:**
- Create: `tests/fixtures/telemetry-2026-09-23/` (`calls.jsonl`, `errors.jsonl`, `details/2026-09-23.jsonl`)
- Test: `tests/test_telemetry_legacy_fixture.py`

**Interfaces:**
- Consumes: `load_calls`, `group_flows`, `apply_rules`, `report_from_logs` (Task 7–12).

- [ ] **Step 1: Chuyển log legacy thành fixture (script một lần, không commit script)** — nguồn: `logs/legacy/telemetry.jsonl` (hoặc `logs/telemetry.jsonl` nếu người dùng chưa chuyển). Chạy:

```bash
uv run python - <<'EOF'
import json, os
src = "logs/legacy/telemetry.jsonl" if os.path.exists("logs/legacy/telemetry.jsonl") else "logs/telemetry.jsonl"
out = "tests/fixtures/telemetry-2026-09-23"
os.makedirs(f"{out}/details", exist_ok=True)
rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.startswith("{")]
day = [r for r in rows if r["ts"].startswith("2026-09-23")]
starts = {r["traceId"]: r for r in day if r["event"] == "tool_start"}
apis = {}
for r in day:
    if r["event"] == "api_call" and r.get("tool"):
        apis.setdefault(r["traceId"], []).append({"method": r["method"], "path": r["path"], "status": r["status"], "durationMs": r["durationMs"]})
ISSUE = ("issue_key", "issue_ref", "issue_id")
with open(f"{out}/calls.jsonl", "w") as calls, open(f"{out}/details/2026-09-23.jsonl", "w") as details, open(f"{out}/errors.jsonl", "w") as errors:
    for r in day:
        if r["event"] != "tool_end" or r["traceId"] not in starts:
            continue
        args = {k: v for k, v in starts[r["traceId"]]["arguments"].items() if v not in ("", None, [], {})}
        issue = next((args[k] for k in ISSUE if k in args), None)
        common = {"v": 3, "ts": starts[r["traceId"]]["ts"], "sessionId": r["client"]["name"], "surface": "mcp", "client": {"name": r["client"]["name"], "version": r["client"].get("version")}}
        calls.write(json.dumps({**common, "traceId": r["traceId"], "tool": r["tool"], "argKeys": sorted(args), "issueKey": issue,
            "projectKey": r.get("project") or None, "mode": args.get("mode"), "status": r["status"], "durationMs": r["durationMs"],
            "apiCalls": len(apis.get(r["traceId"], [])), "apiMs": round(sum(a["durationMs"] for a in apis.get(r["traceId"], [])), 1),
            "responseBytes": r.get("totalResponseBytes", 0), "estTokens": r.get("estimatedTokens", 0), "flags": []}, ensure_ascii=False) + "\n")
        details.write(json.dumps({**common, "traceId": r["traceId"], "tool": r["tool"], "arguments": args, "api": apis.get(r["traceId"], [])}, ensure_ascii=False) + "\n")
print("done", sum(1 for _ in open(f"{out}/calls.jsonl")))
EOF
```

Expected: `done 41`. Ghi chú: `sessionId` của fixture = tên client (log cũ không có session); `result` không có trong log cũ.

- [ ] **Step 2: Viết test** — `tests/test_telemetry_legacy_fixture.py`:

```python
import os

from backlog_tool.telemetry_report import report_from_logs
from backlog_tool.telemetry_rules import apply_rules
from backlog_tool.telemetry_store import group_flows, load_calls

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "telemetry-2026-09-23")


def test_fixture_loads_all_calls():
    calls = load_calls(log_dir=FIXTURE)
    assert len(calls) == 41
    assert sorted({c.client for c in calls}) == ["antigravity-client", "claude-code", "unknown"]


def test_known_findings_from_2026_09_23():
    flows = group_flows(load_calls(log_dir=FIXTURE))
    codes = [f["code"] for flow in flows for f in apply_rules(flow)]
    assert codes.count("generic_after_specialized") == 4
    assert codes.count("duplicate_call") >= 1


def test_report_runs_on_fixture():
    report = report_from_logs(log_dir=FIXTURE)
    assert report["totals"]["calls"] == 41
    assert report["topTools"][0]["tool"] == "resolve_bug"
```

- [ ] **Step 3: Chạy test** — `uv run --extra dev pytest tests/test_telemetry_legacy_fixture.py -q` → PASS. Nếu `generic_after_specialized` ≠ 4, in `[(f.flow_id, f.tools) for f in flows]` và đối chiếu với timeline trong spec §1 trước khi sửa code (không sửa số kỳ vọng cho khớp).

- [ ] **Step 4: Toàn bộ test + lint, commit + push (đóng P2)**

```bash
uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows evals
git add tests/fixtures/telemetry-2026-09-23 tests/test_telemetry_legacy_fixture.py
git commit -m "Verify analysis layer against 2026-09-23 usage fixture

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

---

## Phase P3 — Harness eval

### Task 14: File đánh dấu `.backlog-eval.json`

**Files:**
- Modify: `backlog_tool/settings.py` (thêm `EVAL_MARKER`, `find_eval_marker`, `apply_eval_marker`)
- Modify: `backlog_mcp/server.py` (`main`)
- Test: `tests/test_eval_marker.py`

**Interfaces:**
- Consumes: `telemetry.set_eval_tags`, `telemetry.log_session_start` (Task 2).
- Produces: `settings.find_eval_marker(workspace: str | None) -> dict | None`; `settings.apply_eval_marker(marker: dict) -> None` (đặt `BACKLOG_BASE_URL`, `BACKLOG_API_KEY`, `LOG_DIR`, eval tags; ném `ValueError` nếu host không phải localhost).

- [ ] **Step 1: Viết test fail** — `tests/test_eval_marker.py`:

```python
import json
import os

import pytest

from backlog_tool import settings, telemetry


def write_marker(folder, **overrides):
    marker = {"baseUrl": "http://127.0.0.1:8123", "logDir": str(folder / "logs"), "runId": "r1", "scenario": "open_bugs", **overrides}
    (folder / ".backlog-eval.json").write_text(json.dumps(marker))
    return marker


def test_find_marker_only_in_workspace_root(tmp_path):
    write_marker(tmp_path)
    child = tmp_path / "sub"
    child.mkdir()
    assert settings.find_eval_marker(str(tmp_path))["runId"] == "r1"
    assert settings.find_eval_marker(str(child)) is None
    assert settings.find_eval_marker(None) is None


def test_apply_marker_sets_backend_logs_and_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKLOG_API_KEY", "real-key")
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    marker = write_marker(tmp_path)
    settings.apply_eval_marker(marker)
    assert os.environ["BACKLOG_BASE_URL"] == "http://127.0.0.1:8123"
    assert os.environ["BACKLOG_API_KEY"] == "eval-fake-key"
    assert settings.LOG_DIR == str(tmp_path / "logs")
    telemetry.start_call("get_my_open_bugs", {})
    telemetry.finish_call("ok", result={}, text="", response_bytes=1)
    row = json.loads(open(telemetry.log_paths()["calls"]).readline())
    assert (row["runId"], row["scenario"]) == ("r1", "open_bugs")


@pytest.mark.parametrize("url", ["https://bapjp.backlog.com", "http://10.0.0.5:80", "http://127.0.0.1.evil.com"])
def test_apply_marker_refuses_non_local_backend(tmp_path, url):
    with pytest.raises(ValueError, match="localhost"):
        settings.apply_eval_marker(write_marker(tmp_path, baseUrl=url))
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `AttributeError: find_eval_marker`.

- [ ] **Step 3: Implement trong `backlog_tool/settings.py`** (thêm `from urllib.parse import urlparse`):

```python
EVAL_MARKER = ".backlog-eval.json"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def find_eval_marker(workspace):
    """Eval mode is enabled only by a marker file in the workspace root itself (never a parent)."""
    if not workspace:
        return None
    path = os.path.join(workspace, EVAL_MARKER)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def apply_eval_marker(marker):
    from . import telemetry

    host = urlparse(marker.get("baseUrl", "")).hostname
    if host not in _LOCAL_HOSTS:
        raise ValueError(f"Eval backend must be localhost, got {marker.get('baseUrl')!r}")
    global LOG_DIR
    os.environ["BACKLOG_BASE_URL"] = marker["baseUrl"]
    os.environ["BACKLOG_API_KEY"] = "eval-fake-key"
    LOG_DIR = marker["logDir"]
    telemetry.set_eval_tags(marker.get("runId"), marker.get("scenario"))
```

- [ ] **Step 4: `backlog_mcp/server.py` `main()`**:

```python
def main() -> None:
    """Run the workstation-local server over stdio."""
    workspace = _workspace_path() or os.getcwd()
    marker = find_eval_marker(workspace)
    if marker:
        apply_eval_marker(marker)
    tools = anyio.run(mcp.list_tools)
    log_session_start(backend="fake" if marker else "real", workspace=workspace, tool_count=len(tools))
    mcp.run(transport="stdio")
```

  Thêm `find_eval_marker`, `apply_eval_marker` vào import từ `backlog_tool.settings`. (Nếu `apply_eval_marker` ném `ValueError`, process thoát với traceback trên stderr — đúng yêu cầu "từ chối khởi động".)

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_eval_marker.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backlog_tool/settings.py backlog_mcp/server.py tests/test_eval_marker.py
git commit -m "Enable fake Backlog eval mode via workspace marker file

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 15: Backlog giả

**Files:**
- Create: `evals/fake_backlog.py`
- Test: `tests/test_fake_backlog.py`

**Interfaces:**
- Consumes: `tests/fixtures/OOP_issue_bug.json`, `config/backlog.json` (user `me`), `config/projects/OOP.json`.
- Produces:
  - `build_issues(state: str = "default") -> dict[str, dict]` (key = issueKey)
  - `class FakeBacklog` với `start() -> str` (base URL `http://127.0.0.1:<port>`), `stop()`, `patches: list[dict]` (`{"key", "form"}`), `unhandled: list[dict]` (`{"method", "path"}`); context manager.
  - CLI: `uv run python -m evals.fake_backlog [--state default|no_open_bugs] [--port N]` chạy tới khi Ctrl+C.

- [ ] **Step 1: Viết test fail** — `tests/test_fake_backlog.py`:

```python
import requests

from evals.fake_backlog import FakeBacklog, build_issues


def test_fixtures_shape():
    issues = build_issues()
    assert sorted(issues) == ["OOP-90001", "OOP-90002", "OOP-90003", "OOP-90004", "OOP-90005"]
    for issue in issues.values():
        assert issue["assignee"]["id"] == 778617 and issue["status"]["name"] != "Closed"
        assert issue["issueType"]["name"] == "Bug" and issue["projectId"] == 82531
    role = {c["name"]: c["value"] for c in issues["OOP-90003"]["customFields"]}["Detected Role"]
    assert role["name"] == "Developer"
    assert issues["OOP-90004"]["attachments"][0]["name"] == "login-error.png"


def test_get_list_patch_and_unhandled():
    with FakeBacklog() as fake:
        base = fake.base_url + "/api/v2"
        issue = requests.get(f"{base}/issues/OOP-90001", params={"apiKey": "k"}).json()
        assert issue["issueKey"] == "OOP-90001"
        listed = requests.get(f"{base}/issues", params={"apiKey": "k", "projectId[]": 82531, "assigneeId[]": 778617, "statusId[]": [1, 2]}).json()
        assert sorted(i["issueKey"] for i in listed) == ["OOP-90001", "OOP-90002", "OOP-90003", "OOP-90004", "OOP-90005"]
        patched = requests.patch(f"{base}/issues/OOP-90001", params={"apiKey": "k"}, data={"statusId": 3, "assigneeId": 315996}).json()
        assert patched["status"]["name"] == "Resolved" and patched["assignee"]["id"] == 315996
        assert fake.patches[0]["key"] == "OOP-90001" and fake.patches[0]["form"]["statusId"] == ["3"]
        assert requests.get(f"{base}/issues/OOP-1", params={"apiKey": "k"}).status_code == 404
        assert requests.get(f"{base}/space", params={"apiKey": "k"}).status_code == 404
        assert fake.unhandled == [{"method": "GET", "path": "/api/v2/space"}]


def test_no_open_bugs_state():
    with FakeBacklog(state="no_open_bugs") as fake:
        listed = requests.get(fake.base_url + "/api/v2/issues", params={"apiKey": "k", "assigneeId[]": 778617, "statusId[]": [1, 2, 3]}).json()
        assert listed == []
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError: evals.fake_backlog`.

- [ ] **Step 3: Viết `evals/fake_backlog.py`**

```python
"""Local fake of the Backlog API endpoints the MCP server uses, built from real response fixtures."""

import argparse
import copy
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "OOP_issue_bug.json")
ME = {"id": 778617, "name": "Hieu Nguyen Duy (DN.DEV)"}
REPORTER = {"id": 315996, "name": "tamtt"}
STATUSES = {1: "Open", 2: "In Progress", 3: "Resolved", 4: "Closed"}
EMPTY_FIELDS = {"QC Activity", "Bug Origin", "Cause Category", "Impacted", "Corrective Action"}


def _issue(base, number, summary, description, role="Tester", status_id=1, attachments=None):
    issue = copy.deepcopy(base)
    key = f"OOP-{number}"
    issue.update({
        "id": number, "issueKey": key, "keyId": number, "summary": summary, "description": description,
        "status": {**issue["status"], "id": status_id, "name": STATUSES[status_id]},
        "assignee": {**issue["assignee"], **ME}, "createdUser": {**issue["createdUser"], **REPORTER},
        "startDate": None, "dueDate": None, "estimatedHours": None, "actualHours": None,
        "attachments": attachments or [],
    })
    for field in issue["customFields"]:
        if field["name"] in EMPTY_FIELDS:
            field["value"] = None
        if field["name"] == "Detected Role":
            field["value"] = {"id": 2 if role == "Tester" else 1, "name": role, "displayOrder": 0}
    return issue


TEMPLATE = "**Environment:** DEV\n**Steps to reproduce:**\n1. Open login\n2. Submit\n**Actual:** Error 500\n**Expected:** Logged in\n**Evidence:** see attachment"


def build_issues(state="default"):
    with open(BASE_FIXTURE, encoding="utf-8") as handle:
        base = json.load(handle)
    issues = [
        _issue(base, 90001, "[Admin] Partner dialog overflows on long names", TEMPLATE),
        _issue(base, 90002, "[User] Login shows raw error code", TEMPLATE),
        _issue(base, 90003, "[Admin] Member list misses activation status", TEMPLATE, role="Developer", status_id=2),
        _issue(base, 90004, "[User] Login error after OTP", TEMPLATE,
               attachments=[{"id": 7001, "name": "login-error.png", "size": 48213, "createdUser": REPORTER, "created": "2026-09-20T01:00:00Z"}]),
        _issue(base, 90005, "[Admin] Referral badge shows dash", TEMPLATE),
    ]
    if state == "no_open_bugs":
        # Resolved bugs are reassigned to the reporter, so none remain open for "me".
        for issue in issues:
            issue["status"] = {**issue["status"], "id": 3, "name": "Resolved"}
            issue["assignee"] = {**issue["assignee"], **REPORTER}
    return {issue["issueKey"]: issue for issue in issues}


class _Handler(BaseHTTPRequestHandler):
    fake = None

    def log_message(self, *args):
        return

    def _send(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route(self, method):
        parsed = urlparse(self.path)
        parts = parsed.path.rstrip("/").split("/")
        query = parse_qs(parsed.query)
        issues = self.fake.issues
        if parts[:4] == ["", "api", "v2", "issues"] and len(parts) == 4 and method == "GET":
            statuses = {int(s) for s in query.get("statusId[]", [])}
            assignees = {int(a) for a in query.get("assigneeId[]", [])}
            found = [
                i for i in issues.values()
                if (not statuses or i["status"]["id"] in statuses)
                and (not assignees or i["assignee"]["id"] in assignees)
            ]
            return self._send(200, found)
        if parts[:4] == ["", "api", "v2", "issues"] and len(parts) == 5:
            issue = issues.get(parts[4])
            if issue is None:
                return self._send(404, {"errors": [{"message": "No issue.", "code": 6}]})
            if method == "GET":
                return self._send(200, issue)
            if method == "PATCH":
                length = int(self.headers.get("Content-Length") or 0)
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                self.fake.patches.append({"key": parts[4], "form": form})
                if "statusId" in form:
                    status_id = int(form["statusId"][0])
                    issue["status"] = {**issue["status"], "id": status_id, "name": STATUSES.get(status_id, "?")}
                if "assigneeId" in form:
                    issue["assignee"] = {**issue["assignee"], "id": int(form["assigneeId"][0])}
                return self._send(200, issue)
        if parts[:4] == ["", "api", "v2", "projects"] and len(parts) == 5 and method == "GET":
            return self._send(200, {"id": 82531, "projectKey": parts[4], "name": "OOP"})
        self.fake.unhandled.append({"method": method, "path": parsed.path})
        return self._send(404, {"errors": [{"message": f"fake backlog: unhandled {method} {parsed.path}"}]})

    def do_GET(self):
        self._route("GET")

    def do_PATCH(self):
        self._route("PATCH")

    def do_POST(self):
        self._route("POST")


class FakeBacklog:
    def __init__(self, state="default", port=0):
        self.state = state
        self.port = port
        self.issues = build_issues(state)
        self.patches = []
        self.unhandled = []
        self._server = None
        self.base_url = None

    def start(self):
        handler = type("Handler", (_Handler,), {"fake": self})
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        return self.base_url

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


def main():
    parser = argparse.ArgumentParser(description="Run the fake Backlog API for manual MCP testing.")
    parser.add_argument("--state", default="default", choices=["default", "no_open_bugs"])
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    fake = FakeBacklog(args.state, args.port)
    print(f"Fake Backlog at {fake.start()} (Ctrl+C to stop)", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        fake.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Chạy test** — `uv run --extra dev pytest tests/test_fake_backlog.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/fake_backlog.py tests/test_fake_backlog.py
git commit -m "Add fake Backlog API for evals

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 16: Replay test qua stdio

**Files:**
- Create: `tests/test_replay.py`

**Interfaces:**
- Consumes: `FakeBacklog` (Task 15), marker (Task 14), `load_scenarios`/`render_scenario`/`grade` (Task 9), `load_calls`/`group_flows` (Task 7).

- [ ] **Step 1: Viết test** — `tests/test_replay.py`:

```python
"""Replay each scenario's expected MCP calls against the real server (stdio) on the fake backend.

No model involved. Proves the server + fake backend can satisfy each scenario and that
the logs grade as PASS. Scenarios that need Plan B (P5) behavior are xfail until then.
"""

import json
import os
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backlog_tool.telemetry_grader import grade, load_scenarios, render_scenario
from backlog_tool.telemetry_store import group_flows, load_calls
from evals.fake_backlog import FakeBacklog

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NEEDS_PLAN_B = {
    "resolve_fixed": "apply without fix_description is rejected until P5",
    "resolve_multi": "apply without fix_description is rejected until P5",
    "resolve_warning": "apply without fix_description is rejected until P5",
    "fix_context_attachment": "get_bug_context lists attachments in P5",
}


async def _replay(workspace, calls):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backlog_mcp.server"],
        cwd=str(workspace),
        env={**os.environ, "PYTHONPATH": ROOT, "BACKLOG_WORKSPACE_PATH": str(workspace)},
    )
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for expected in calls:
                results.append(await session.call_tool(expected["tool"], expected["args"]))
    return results


@pytest.mark.parametrize("scenario_id", [s["id"] for s in load_scenarios()])
def test_replay_scenario(scenario_id, tmp_path, request):
    if scenario_id in NEEDS_PLAN_B:
        request.applymarker(pytest.mark.xfail(reason=NEEDS_PLAN_B[scenario_id], strict=True))
    scenario = render_scenario(next(s for s in load_scenarios() if s["id"] == scenario_id))
    log_dir = tmp_path / "eval-logs"
    with FakeBacklog(state=scenario["fakeState"]) as fake:
        (tmp_path / ".backlog-project.json").write_text(json.dumps({"project_key": "OOP"}))
        (tmp_path / ".backlog-eval.json").write_text(json.dumps({
            "baseUrl": fake.base_url, "logDir": str(log_dir), "runId": "replay-1", "scenario": scenario_id,
        }))
        results = anyio.run(_replay, tmp_path, scenario["expect"]["calls"])
        assert fake.unhandled == []

    assert all(not r.isError for r in results), [r.content[0].text for r in results if r.isError]
    [flow] = group_flows(load_calls(log_dir=str(log_dir)))
    graded = grade(scenario["expect"], flow, final_answer=None)
    assert graded["pass"] is True, graded["reasons"]
    if scenario_id == "fix_context_attachment":
        assert "login-error.png" in json.dumps(results[0].structuredContent)
```

- [ ] **Step 2: Chạy** — `uv run --extra dev pytest tests/test_replay.py -q`
Expected: 3 PASS (`open_bugs`, `open_bugs_empty`, `fix_context`), 4 XFAIL. Nếu `open_bugs_empty` fail vì `finalAnswer` — `grade` với `final_answer=None` trả `{"skipped": …}` và không fail; nếu kịch bản nào PASS ngoài dự kiến (XPASS strict) → đọc lý do, bỏ khỏi `NEEDS_PLAN_B` nếu đúng là đã thoả.

- [ ] **Step 3: Commit**

```bash
git add tests/test_replay.py
git commit -m "Replay eval scenarios through the stdio server on the fake backend

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 17: Adapter agent và parser stream-json

**Files:**
- Create: `evals/agents.py`
- Create: `tests/fixtures/agent_streams/claude_sample.jsonl`, `tests/fixtures/agent_streams/agy_sample.jsonl`
- Test: `tests/test_eval_agents.py`

**Interfaces:**
- Produces:
  - `@dataclass AgentTrace(model, final_answer, mcp_tools: list[dict], non_mcp: list[dict], schema_reads: int, denied: list, wall_clock_ms, turns, raw_ok: bool)`; `mcp_tools` phần tử `{"tool", "arguments"}`.
  - `claude_command(prompt, model) -> list[str]`; `agy_command(prompt, model, timeout_s) -> list[str]`
  - `parse_claude(lines: list[str]) -> AgentTrace`; `parse_agy(lines: list[str]) -> AgentTrace`
  - `AGENTS = {"claude": (claude_command, parse_claude), "agy": (agy_command, parse_agy)}`

- [ ] **Step 1: Tạo fixture stream** — định dạng lấy từ probe thật 2026-09-24.

`tests/fixtures/agent_streams/claude_sample.jsonl`:
```jsonl
{"type":"system","subtype":"hook_started","hook_name":"SessionStart:startup"}
{"type":"system","subtype":"init","cwd":"/tmp/ws","model":"claude-opus-5-5[1m]","mcp_servers":[{"name":"backlog","status":"connected"}]}
{"type":"assistant","message":{"model":"claude-opus-5-5","content":[{"type":"tool_use","id":"t1","name":"Grep","input":{"pattern":"fix"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"none","is_error":false}]}}
{"type":"assistant","message":{"model":"claude-opus-5-5","content":[{"type":"tool_use","id":"t2","name":"mcp__backlog__resolve_bug","input":{"issue_key":"OOP-90001","mode":"apply"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":[{"type":"text","text":"{}"}],"is_error":false}]}}
{"type":"assistant","message":{"model":"claude-opus-5-5","content":[{"type":"text","text":"Đã resolve OOP-90001."}]}}
{"type":"result","subtype":"success","is_error":false,"duration_ms":9120,"num_turns":3,"result":"Đã resolve OOP-90001.","permission_denials":[{"tool_name":"Bash","tool_use_id":"t0","tool_input":{"command":"git log -1"}}]}
```

`tests/fixtures/agent_streams/agy_sample.jsonl`:
```jsonl
{"event":"init","conversation_id":"c1","init":{"cwd":"/tmp/ws","tools":["call_mcp_tool","view_file"],"permission_mode":"always-proceed"}}
{"event":"step_update","step_update":{"step_index":0,"state":"DONE","step_type":"user_input"}}
{"event":"step_update","step_update":{"step_index":2,"state":"DONE","step_type":"tool","tool_name":"view_file","tool_info":{"name":"view_file","parameters":{"AbsolutePath":"/home/u/.gemini/antigravity-cli/mcp/backlog/resolve_bug.json"},"output":"1 lines"}}}
{"event":"step_update","step_update":{"step_index":4,"state":"DONE","step_type":"tool","tool_name":"call_mcp_tool","tool_info":{"name":"call_mcp_tool","parameters":{"Arguments":{"issue_key":"OOP-90001","mode":"apply"},"ServerName":"backlog","ToolName":"resolve_bug"},"output":"{}"}}}
{"event":"step_update","step_update":{"step_index":6,"state":"DONE","step_type":"tool","tool_name":"run_command","tool_info":{"name":"run_command","parameters":{"CommandLine":"ls"},"output":""}}}
{"event":"result","result":{"conversation_id":"c1","status":"SUCCESS","response":"Đã resolve OOP-90001.\n","duration_seconds":12.5,"num_turns":4}}
```

- [ ] **Step 2: Viết test fail** — `tests/test_eval_agents.py`:

```python
import os

from evals.agents import agy_command, claude_command, parse_agy, parse_claude

STREAMS = os.path.join(os.path.dirname(__file__), "fixtures", "agent_streams")


def lines(name):
    with open(os.path.join(STREAMS, name), encoding="utf-8") as handle:
        return handle.readlines()


def test_parse_claude():
    trace = parse_claude(lines("claude_sample.jsonl"))
    assert trace.model == "claude-opus-5-5"
    assert trace.mcp_tools == [{"tool": "resolve_bug", "arguments": {"issue_key": "OOP-90001", "mode": "apply"}}]
    assert trace.non_mcp == [{"name": "Grep", "input": {"pattern": "fix"}}]
    assert trace.denied == ["Bash"]
    assert trace.final_answer == "Đã resolve OOP-90001."
    assert trace.wall_clock_ms == 9120 and trace.turns == 3 and trace.raw_ok is True


def test_parse_agy():
    trace = parse_agy(lines("agy_sample.jsonl"))
    assert trace.mcp_tools == [{"tool": "resolve_bug", "arguments": {"issue_key": "OOP-90001", "mode": "apply"}}]
    assert trace.schema_reads == 1
    assert trace.non_mcp == [{"name": "run_command", "input": {"CommandLine": "ls"}}]
    assert trace.final_answer == "Đã resolve OOP-90001."
    assert trace.wall_clock_ms == 12500 and trace.raw_ok is True


def test_parse_truncated_stream_is_not_ok():
    trace = parse_agy(lines("agy_sample.jsonl")[:-1])
    assert trace.raw_ok is False and trace.final_answer is None


def test_commands_restrict_tools_and_use_stream_json():
    claude = claude_command("p", "opus")
    assert claude[:2] == ["claude", "-p"] and "--disallowedTools" in claude and "stream-json" in claude
    agy = agy_command("p", "gemini-3.8-flash-medium", 300)
    assert "--sandbox" in agy and "--dangerously-skip-permissions" in agy and "--model" in agy
```

- [ ] **Step 3: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError: evals.agents`.

- [ ] **Step 4: Viết `evals/agents.py`**

```python
"""Commands and stream-json parsers for the agents we evaluate (Claude Code, Antigravity CLI)."""

import json
from dataclasses import dataclass, field

CLAUDE_MCP_PREFIX = "mcp__backlog__"
# In the user's auto permission mode --allowedTools does not block other tools; deny explicitly.
CLAUDE_DISALLOWED = ["Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"]
AGY_SCHEMA_DIR = "/.gemini/antigravity-cli/mcp/backlog/"


@dataclass
class AgentTrace:
    model: str | None = None
    final_answer: str | None = None
    mcp_tools: list = field(default_factory=list)
    non_mcp: list = field(default_factory=list)
    schema_reads: int = 0
    denied: list = field(default_factory=list)
    wall_clock_ms: float | None = None
    turns: int | None = None
    raw_ok: bool = False


def _events(lines):
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def claude_command(prompt, model):
    return [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--disallowedTools", *CLAUDE_DISALLOWED,
    ]


def agy_command(prompt, model, timeout_s):
    return [
        "agy", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions", "--sandbox",
        "--print-timeout", f"{int(timeout_s)}s",
    ]


def parse_claude(lines):
    trace = AgentTrace()
    for event in _events(lines):
        kind = event.get("type")
        if kind == "assistant":
            message = event.get("message") or {}
            trace.model = message.get("model") or trace.model
            for part in message.get("content") or []:
                if part.get("type") != "tool_use":
                    continue
                name = part.get("name") or ""
                if name.startswith(CLAUDE_MCP_PREFIX):
                    trace.mcp_tools.append({"tool": name[len(CLAUDE_MCP_PREFIX):], "arguments": part.get("input") or {}})
                else:
                    trace.non_mcp.append({"name": name, "input": part.get("input") or {}})
        elif kind == "result":
            trace.final_answer = event.get("result")
            trace.wall_clock_ms = event.get("duration_ms")
            trace.turns = event.get("num_turns")
            trace.denied = [d.get("tool_name") for d in event.get("permission_denials") or []]
            trace.raw_ok = not event.get("is_error")
    return trace


def parse_agy(lines):
    trace = AgentTrace()
    for event in _events(lines):
        if event.get("event") == "step_update":
            step = event["step_update"]
            if step.get("state") != "DONE" or step.get("step_type") != "tool":
                continue
            info = step.get("tool_info") or {}
            params = info.get("parameters") or {}
            name = step.get("tool_name")
            if name == "call_mcp_tool" and params.get("ServerName") == "backlog":
                trace.mcp_tools.append({"tool": params.get("ToolName"), "arguments": params.get("Arguments") or {}})
            elif name == "view_file" and AGY_SCHEMA_DIR in (params.get("AbsolutePath") or ""):
                trace.schema_reads += 1
            else:
                trace.non_mcp.append({"name": name, "input": params})
        elif event.get("event") == "result":
            result = event["result"]
            trace.final_answer = (result.get("response") or "").strip() or None
            seconds = result.get("duration_seconds")
            trace.wall_clock_ms = round(seconds * 1000) if seconds is not None else None
            trace.turns = result.get("num_turns")
            trace.raw_ok = result.get("status") == "SUCCESS"
    return trace


AGENTS = {
    "claude": (claude_command, parse_claude),
    "agy": (agy_command, parse_agy),
}
```

- [ ] **Step 5: Chạy test** — `uv run --extra dev pytest tests/test_eval_agents.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add evals/agents.py tests/fixtures/agent_streams tests/test_eval_agents.py
git commit -m "Add Claude and agy command builders and stream parsers

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 18: Runner eval, chạy thử thật, tài liệu (đóng P3)

**Files:**
- Create: `evals/run.py`
- Test: `tests/test_eval_run.py`
- Modify: `docs/telemetry.md` (mục "Eval"), `.gitignore` (không bỏ qua `evals/results/`)

**Interfaces:**
- Consumes: Task 9 (`load_scenarios`, `render_scenario`, `grade`), Task 7 (`load_calls`, `group_flows`, `Flow`), Task 15 (`FakeBacklog`), Task 17 (`AGENTS`, `AgentTrace`).
- Produces:
  - `config_fingerprint(agent: str) -> {"agentVersion", "gitSha", "toolsHash", "toolCount"}` (gắn vào mọi dòng kết quả)
  - `prepare_workspace(root: Path, scenario: dict, run_id: str, base_url: str, log_dir: Path) -> Path`
  - `grade_run(scenario: dict, trace: AgentTrace, log_dir: Path, run_id: str) -> dict` (kết quả §7.4 + `schemaReads`, `deniedTools`, `nonMcpCalls`, `wallClockMs`, `turns`, `agentOk`, `mcpCallsSeenByAgent`)
  - `run_one(agent: str, model: str, scenario: dict, index: int, out_root: Path, timeout_s: int) -> dict`
  - `main(argv=None)` — CLI `uv run python -m evals.run --agent claude|agy --model M --scenario ID|all --runs N [--label L] [--timeout 300] [--workspace PATH]`; ghi `evals/results/<YYYY-MM-DD>-<label>/<agent>-<model>.jsonl` (một dòng/run, ghi ngay sau mỗi run) và `SUMMARY.md` (bảng pass-rate theo kịch bản cho mọi file trong thư mục).

- [ ] **Step 1: Viết test fail** — `tests/test_eval_run.py` (không gọi agent thật; dùng log giả do telemetry ghi):

```python
import json

from backlog_tool import settings, telemetry
from backlog_tool.telemetry_grader import load_scenarios, render_scenario
from evals.agents import AgentTrace
from evals.run import grade_run, prepare_workspace, write_summary


def scenario(scenario_id):
    return render_scenario(next(s for s in load_scenarios() if s["id"] == scenario_id))


def test_prepare_workspace_writes_markers(tmp_path):
    ws = prepare_workspace(tmp_path, scenario("resolve_fixed"), "run-1", "http://127.0.0.1:9", tmp_path / "logs")
    marker = json.loads((ws / ".backlog-eval.json").read_text())
    assert marker == {"baseUrl": "http://127.0.0.1:9", "logDir": str(tmp_path / "logs"), "runId": "run-1", "scenario": "resolve_fixed"}
    assert json.loads((ws / ".backlog-project.json").read_text()) == {"project_key": "OOP"}


def test_grade_run_combines_logs_and_agent_trace(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(settings, "LOG_DIR", str(log_dir))
    telemetry.set_eval_tags("run-1", "resolve_warning")
    telemetry.start_call("resolve_bug", {"issue_key": "OOP-90003", "mode": "apply"})
    telemetry.finish_call("ok", result={"ok": True}, text="{}", response_bytes=300)
    telemetry.set_eval_tags(None, None)

    trace = AgentTrace(model="m", final_answer="Resolved. Warning: Detected Role is Developer, not Tester",
                       mcp_tools=[{"tool": "resolve_bug", "arguments": {}}], schema_reads=2,
                       non_mcp=[{"name": "Grep", "input": {}}], denied=["Bash"], wall_clock_ms=8000, turns=3, raw_ok=True)
    result = grade_run(scenario("resolve_warning"), trace, log_dir, "run-1")
    assert result["pass"] is True
    assert result["schemaReads"] == 2 and result["deniedTools"] == ["Bash"] and result["nonMcpCalls"] == ["Grep"]
    assert result["agentOk"] is True and result["mcpCallsSeenByAgent"] == 1


def test_grade_run_with_no_calls_fails(tmp_path):
    trace = AgentTrace(final_answer="Tôi cần thêm thông tin.", raw_ok=True)
    result = grade_run(scenario("fix_context"), trace, tmp_path / "logs", "run-x")
    assert result["pass"] is False and result["reasons"]


def test_write_summary(tmp_path):
    rows = [{"scenario": "open_bugs", "pass": True}, {"scenario": "open_bugs", "pass": False, "reasons": ["extra calls: ['get_issues']"]}]
    (tmp_path / "claude-opus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    text = (tmp_path / "SUMMARY.md").read_text()
    assert "| open_bugs | 1/2 |" in text and "claude-opus" in text and "extra calls ×1" in text
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ModuleNotFoundError: evals.run`.

- [ ] **Step 3: Viết `evals/run.py`**

```python
"""Run eval scenarios through a real agent (claude/agy) against the fake Backlog and grade the logs."""

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

from backlog_tool.telemetry_grader import grade, load_scenarios, render_scenario
from backlog_tool.telemetry_store import Flow, group_flows, load_calls
from evals.agents import AGENTS, AgentTrace
from evals.fake_backlog import FakeBacklog

RESULTS_ROOT = Path(__file__).resolve().parent / "results"


def config_fingerprint(agent):
    """Which agent build, server code and tool descriptions produced a run."""
    import hashlib

    import anyio

    from backlog_mcp import server
    from backlog_tool.telemetry import server_version

    try:
        agent_version = subprocess.run([agent, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        agent_version = None
    tools = anyio.run(server.mcp.list_tools)
    described = json.dumps([[t.name, t.description, t.inputSchema] for t in tools], sort_keys=True, ensure_ascii=False)
    return {
        "agentVersion": agent_version,
        "gitSha": server_version()["gitSha"],
        "toolsHash": hashlib.sha256(described.encode("utf-8")).hexdigest()[:12],
        "toolCount": len(tools),
    }


def prepare_workspace(root, scenario, run_id, base_url, log_dir):
    workspace = Path(root)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".backlog-project.json").write_text(json.dumps({"project_key": "OOP"}))
    (workspace / ".backlog-eval.json").write_text(json.dumps({
        "baseUrl": base_url, "logDir": str(log_dir), "runId": run_id, "scenario": scenario["id"],
    }))
    return workspace


def grade_run(scenario, trace, log_dir, run_id):
    flows = group_flows(load_calls(log_dir=str(log_dir), run_id=run_id)) if Path(log_dir).exists() else []
    flow = flows[0] if flows else Flow(run_id, [])
    result = grade(scenario["expect"], flow, final_answer=trace.final_answer)
    result.update({
        "schemaReads": trace.schema_reads,
        "deniedTools": trace.denied,
        "nonMcpCalls": [item["name"] for item in trace.non_mcp],
        "wallClockMs": trace.wall_clock_ms,
        "turns": trace.turns,
        "agentOk": trace.raw_ok,
        "mcpCallsSeenByAgent": len(trace.mcp_tools),
        "finalAnswer": (trace.final_answer or "")[:500],
    })
    return result


def run_one(agent, model, scenario, index, out_root, timeout_s, workspace=None):
    build_command, parse = AGENTS[agent]
    run_id = f"{agent}-{scenario['id']}-{index}-{uuid.uuid4().hex[:6]}"
    with tempfile.TemporaryDirectory(prefix="backlog-eval-") as tmp:
        root = Path(workspace) if workspace else Path(tmp) / "ws"
        log_dir = Path(tmp) / "logs"
        with FakeBacklog(state=scenario["fakeState"]) as fake:
            ws = prepare_workspace(root, scenario, run_id, fake.base_url, log_dir)
            started = time.monotonic()
            try:
                proc = subprocess.run(
                    build_command(scenario["prompt"], model) if agent == "claude" else build_command(scenario["prompt"], model, timeout_s),
                    cwd=ws, capture_output=True, text=True, timeout=timeout_s + 30,
                )
                lines = proc.stdout.splitlines()
                stderr_tail = proc.stderr[-2000:]
            except subprocess.TimeoutExpired as error:
                lines = (error.stdout or b"").decode("utf-8", "replace").splitlines() if isinstance(error.stdout, bytes) else (error.stdout or "").splitlines()
                stderr_tail = "timeout"
            elapsed_ms = round((time.monotonic() - started) * 1000)
            trace = parse(lines)
            result = grade_run(scenario, trace, log_dir, run_id)
            result.update({
                "runId": run_id, "agent": agent, "model": model, "scenario": scenario["id"],
                "processMs": elapsed_ms, "unhandledEndpoints": fake.unhandled,
                "patches": [p["key"] for p in fake.patches], "stderrTail": stderr_tail if not trace.raw_ok else "",
            })
            if workspace:
                for marker in (".backlog-eval.json", ".backlog-project.json"):
                    (ws / marker).unlink(missing_ok=True)
    return result


def write_summary(folder):
    folder = Path(folder)
    lines = [f"# Eval summary — {folder.name}", ""]
    for path in sorted(folder.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        by_scenario = defaultdict(lambda: [0, 0])
        reasons = defaultdict(int)
        for row in rows:
            by_scenario[row["scenario"]][1] += 1
            by_scenario[row["scenario"]][0] += int(bool(row.get("pass")))
            for reason in row.get("reasons") or []:
                reasons[reason.split(":")[0]] += 1
        lines += [f"## {path.stem}", "", "| Scenario | Pass/Runs |", "|---|---|"]
        lines += [f"| {scenario} | {ok}/{total} |" for scenario, (ok, total) in sorted(by_scenario.items())]
        if reasons:
            lines += ["", "Lý do fail phổ biến: " + ", ".join(f"{k} ×{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))]
        lines.append("")
    (folder / "SUMMARY.md").write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Backlog MCP eval scenarios through a real agent.")
    parser.add_argument("--agent", required=True, choices=sorted(AGENTS))
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--label", default="adhoc")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workspace", help="Run inside this directory instead of a temp workspace")
    args = parser.parse_args(argv)

    scenarios = [render_scenario(s) for s in load_scenarios() if args.scenario in ("all", s["id"])]
    folder = RESULTS_ROOT / f"{date.today().isoformat()}-{args.label}"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{args.agent}-{args.model}.jsonl"
    fingerprint = config_fingerprint(args.agent)
    for scenario in scenarios:
        for index in range(args.runs):
            result = run_one(args.agent, args.model, scenario, index, folder, args.timeout, args.workspace)
            result["configFingerprint"] = fingerprint
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            status = "PASS" if result["pass"] else "FAIL " + "; ".join(result["reasons"])[:120]
            print(f"[{scenario['id']} #{index + 1}] {status}", flush=True)
    write_summary(folder)
    print(f"Results: {out}\nSummary: {folder / 'SUMMARY.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Chạy test** — `uv run --extra dev pytest tests/test_eval_run.py -q` → PASS; rồi toàn bộ: `uv run --extra dev pytest -q && uvx ruff check --select F backlog_mcp backlog_tool workflows evals` → PASS.

- [ ] **Step 5: Chạy thử thật (smoke, tốn quota nhỏ)**

```bash
uv run python -m evals.run --agent claude --model opus --scenario open_bugs --runs 1 --label smoke
uv run python -m evals.run --agent agy --model gemini-3.8-flash-medium --scenario open_bugs --runs 1 --label smoke
```

Expected: mỗi lệnh in một dòng `[open_bugs #1] PASS` hoặc `FAIL …` (kết quả pass/fail chưa quan trọng ở P3) và tạo `evals/results/<ngày>-smoke/{claude-opus,agy-gemini-3.8-flash-medium}.jsonl` với `agentOk: true`, `unhandledEndpoints: []`, `mcpCallsSeenByAgent ≥ 1`. Nếu `mcpCallsSeenByAgent == 0` và log run rỗng: kiểm tra `sessions.jsonl` trong log dir tạm có `backend: "fake"` không (server có thấy marker không) — đọc stderrTail; sửa trước khi đóng P3. Nếu agy báo không khởi động được MCP server khi có `--sandbox`, bỏ `--sandbox` khỏi `agy_command` (và test tương ứng), ghi lý do vào `docs/telemetry.md` mục Eval.

- [ ] **Step 6: Tài liệu** — thêm mục cuối `docs/telemetry.md`:

````markdown
## Eval
- Kịch bản: `evals/scenarios.json`. Backlog giả: `uv run python -m evals.fake_backlog [--state no_open_bugs]`.
- Chạy: `uv run python -m evals.run --agent claude|agy --model <m> --scenario <id|all> --runs N --label <nhãn>`.
- Server bật chế độ giả khi workspace có `.backlog-eval.json` (`baseUrl` phải là localhost); log run ghi vào `logDir` của file đó, gắn `runId`/`scenario`.
- `claude` chạy với `--disallowedTools Bash Edit Write NotebookEdit WebFetch WebSearch`; `agy` chạy với `--sandbox`. Tool bị từ chối nằm ở `deniedTools`.
- agy gọi MCP qua `call_mcp_tool` và đọc schema bằng `view_file` trong `~/.gemini/antigravity-cli/mcp/backlog/` → đếm ở `schemaReads`.
- Kết quả: `evals/results/<ngày>-<nhãn>/<agent>-<model>.jsonl` (một dòng/run) và `SUMMARY.md`.
- Replay không dùng model: `uv run --extra dev pytest tests/test_replay.py`.
````

  Kiểm tra `.gitignore` không bỏ qua `evals/results/` (`git check-ignore evals/results/x.jsonl` → không in gì).

- [ ] **Step 7: Commit + push (đóng P3)**

```bash
git add evals/run.py tests/test_eval_run.py docs/telemetry.md evals/results
git commit -m "Add eval runner with smoke results for claude and agy

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

Điều kiện đóng P3 (spec §10): replay test 3 PASS + 4 XFAIL; smoke run mỗi agent ra file kết quả hợp lệ (`agentOk`, `unhandledEndpoints: []`, server chạy `backend: fake`). Sau đó viết Plan B (P4–P6).
