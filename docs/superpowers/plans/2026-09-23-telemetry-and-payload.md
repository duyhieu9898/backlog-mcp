# Telemetry Precision & Payload Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Làm cho telemetry đủ chính xác để kiểm chứng hành vi thật (session, phiên bản server, preview↔apply, trạng thái trước/sau, CLI), gọn lại nguồn log, rồi giảm token của `get_bug_context` / `get_my_open_bugs` và đo được mức giảm trên log thật.

**Architecture:** `telemetry.jsonl` là nguồn sự thật duy nhất. Mỗi record có thêm `sessionId` + `surface`; process MCP ghi `server_start` (git sha). Mutation `resolve_bug` ghi thêm event `mutation` (planHash, statusBefore/After) gắn vào trace hiện tại. CLI ghi `tool_start`/`tool_end` như MCP. Analyzer dùng các field mới, fallback heuristic cho record cũ. Lệnh `backlog-cli telemetry report` là công cụ kiểm chứng cho mọi phase.

**Tech Stack:** Python ≥3.10, `mcp` FastMCP (stdio), `requests`, pytest. Không thêm dependency.

**Spec:** Phân tích trong phiên 2026-09-23 (log metric + lịch sử commit). Các con số baseline bên dưới được đo từ `logs/telemetry.jsonl` ngày 2026-09-23.

## Global Constraints

- Commit thẳng lên `main`, `git push origin main` sau mỗi phase. Không tạo branch, không tạo PR.
- Mỗi commit kết thúc bằng: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
- Không thêm dependency vào `pyproject.toml`.
- Không bao giờ ghi API key hoặc URL đầy đủ có query string vào bất kỳ log nào.
- Ghi log không được làm hỏng tool call: mọi lỗi ghi log đi qua `settings.report_log_failure` (đã có).
- Chỉ thêm field vào telemetry (additive); giữ `schemaVersion = 2`; analyzer phải đọc được record cũ.
- stdout của MCP server chỉ dành cho giao thức; chỉ ghi stderr.
- Chạy test: `uv run --extra dev pytest -q` (hiện 160 test pass).

## Baseline (2026-09-23, đo trên log thật)

| Chỉ số | Giá trị |
|---|---|
| MCP tool call / Backlog API call | 41 / 58 |
| `get_bug_context` token TB | ~1215 (10 call) |
| trong đó `rawDescription` trùng lặp | 30–40% payload |
| trong đó `customFields` raw | ~1 KB/bug (~25%) |
| `get_my_open_bugs` | 4087 token cho 6 bug (~681/bug) |
| `get_issue` ngay sau `get_bug_context` cùng issue | 4 lần (~4k token) |
| `apply_without_preview` (analyzer) | 8 / 15 apply |
| API call mồ côi (`tool: null`, do CLI) | 22 (toàn bộ log) |
| `responseBody` / tổng dung lượng telemetry | 64% (511 KB / 798 KB) |

## Review Focus

1. **Preview hôm trước, apply hôm sau**: payload chứa `startDate`/`dueDate` theo ngày nên `planHash` khác → apply bị coi là không có preview. Chấp nhận, nhưng phải có test chứng minh hash ổn định khi input giống nhau và thay đổi khi payload đổi (Task 3).
2. **Log trộn record cũ (không `sessionId`, không `mutation`) và mới**: analyzer không được crash và phải fallback về heuristic cũ (Task 5).
3. **Máy không có git / thư mục không phải repo**: `server_version()` trả `None`, server vẫn khởi động (Task 2).
4. **Description có chữ trước marker template, hoặc không có marker**: không được mất nội dung khi bỏ `rawDescription` (Task 8).
5. **Lệnh CLI lỗi (config sai, API 4xx)**: vẫn phải ghi `tool_end` status `error`, không để trace treo (Task 4).

---

## Phase 0 — Chuẩn bị kiểm chứng

### Task 0: Dọn record test cũ khỏi log thật (người dùng tự chạy)

Record do pytest ghi trước commit `47b3023` (2026-09-22 17:59) nằm trong 6 "đợt" mỗi đợt đúng 1 giây. Bước này ghi đè file log thật nên **người dùng tự chạy**, agent không chạy.

- [ ] **Step 1: Lưu script vào scratch (không commit)**

```python
# purge_test_telemetry.py — chạy từ root repo
import glob, json, os, shutil, sys

APPLY = "--apply" in sys.argv
BURSTS = {
    "2026-09-21T16:22:58", "2026-09-21T17:10:15", "2026-09-22T10:57:53",
    "2026-09-22T11:00:19", "2026-09-22T16:11:36", "2026-09-22T17:57:51",
}
CUTOFF = "2026-09-22T17:59:08"  # conftest log isolation (47b3023)
BACKUP = "logs/_backup_before_test_purge_2026-09-23"


def lines(path):
    with open(path, encoding="utf-8") as handle:
        return [line for line in handle if line.strip()]


telemetry = [json.loads(line) for line in lines("logs/telemetry.jsonl")]
bad_traces = {r["traceId"] for r in telemetry if r["ts"][:19] in BURSTS}


def is_test(record, by_trace):
    if record["ts"] >= CUTOFF:
        return False
    return record["ts"][:19] in BURSTS or (by_trace and record.get("traceId") in bad_traces)


plan = {"logs/telemetry.jsonl": True, "logs/metrics.log": False, "logs/backlog.log": False}
plan.update({path: False for path in glob.glob("logs/sessions/*.jsonl")})
for path, by_trace in plan.items():
    rows = lines(path)
    keep = [row for row in rows if not is_test(json.loads(row), by_trace)]
    print(f"{path}: {len(rows)} -> {len(keep)} (drop {len(rows) - len(keep)})")
    if APPLY and len(keep) != len(rows):
        os.makedirs(BACKUP, exist_ok=True)
        shutil.copy2(path, os.path.join(BACKUP, os.path.basename(path)))
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(keep)
```

- [ ] **Step 2: Dry-run** — `python3 purge_test_telemetry.py`. Kỳ vọng: telemetry drop ≈176, metrics ≈68, backlog ≈92, sessions 0.
- [ ] **Step 3: Apply** — `python3 purge_test_telemetry.py --apply`. Bản gốc nằm trong `logs/_backup_before_test_purge_2026-09-23/`.

### Task 1: Lệnh `backlog-cli telemetry report`

**Files:**
- Create: `backlog_tool/telemetry_report.py`
- Modify: `backlog_tool/cli.py` (`build_parser`, `run_handler`, docstring đầu file)
- Test: `tests/test_telemetry_report.py`

**Interfaces:**
- Produces: `build_report(records: list[dict], since: str) -> dict` với key `since, toolCalls, apiCalls, orphanApiCalls, clients, sessions, responseBodyChars, tools, findingCounts`. `tools[name]` có `calls, errors, estimatedTokens, avgTokens, avgDurationMs`.
- CLI: `uv run backlog-cli --json-full telemetry report --since 2026-09-24`

- [ ] **Step 1: Viết test fail**

```python
# tests/test_telemetry_report.py
from backlog_tool.telemetry_report import build_report


def rec(ts, event, trace, tool, **extra):
    return {"schemaVersion": 2, "ts": ts, "event": event, "traceId": trace, "tool": tool,
            "client": {"name": "claude-code", "version": "t", "transport": "stdio"}, **extra}


def test_report_filters_by_since_and_aggregates_tools():
    records = [
        rec("2026-09-22T10:00:00+07:00", "tool_start", "old", "get_issue", arguments={}),
        rec("2026-09-22T10:00:01+07:00", "tool_end", "old", "get_issue", status="ok", estimatedTokens=999, durationMs=5),
        rec("2026-09-24T10:00:00+07:00", "tool_start", "a", "get_bug_context", arguments={"issue_key": "OOP-1"}, sessionId="s1"),
        rec("2026-09-24T10:00:01+07:00", "api_call", "a", "get_bug_context", responseBody="x" * 10),
        rec("2026-09-24T10:00:02+07:00", "tool_end", "a", "get_bug_context", status="ok", estimatedTokens=100, durationMs=10),
        rec("2026-09-24T10:01:00+07:00", "api_call", "b", None),
        rec("2026-09-24T10:02:00+07:00", "tool_start", "c", "get_bug_context", arguments={"issue_key": "OOP-2"}, sessionId="s1"),
        rec("2026-09-24T10:02:01+07:00", "tool_end", "c", "get_bug_context", status="error", estimatedTokens=20, durationMs=30),
    ]

    report = build_report(records, "2026-09-24")

    assert report["toolCalls"] == 2
    assert report["apiCalls"] == 2
    assert report["orphanApiCalls"] == 1
    assert report["sessions"] == 1
    assert report["responseBodyChars"] == 10
    row = report["tools"]["get_bug_context"]
    assert row == {"calls": 2, "errors": 1, "estimatedTokens": 120, "avgTokens": 60, "avgDurationMs": 20}
    assert "get_issue" not in report["tools"]
    assert isinstance(report["findingCounts"], dict)
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_telemetry_report.py -q` → `ModuleNotFoundError: backlog_tool.telemetry_report`.

- [ ] **Step 3: Implement**

```python
# backlog_tool/telemetry_report.py
"""Compact telemetry report used to verify telemetry/payload changes on real logs."""

from collections import Counter, defaultdict

from .workflow_efficiency import summarize_workflow_efficiency


def build_report(records, since):
    records = [record for record in records if (record.get("ts") or "") >= since]
    ends = [record for record in records if record.get("event") == "tool_end"]
    api_calls = [record for record in records if record.get("event") == "api_call"]

    tools = defaultdict(lambda: {"calls": 0, "errors": 0, "estimatedTokens": 0, "_durationMs": 0.0})
    for record in ends:
        row = tools[record.get("tool") or "unknown"]
        row["calls"] += 1
        row["errors"] += int(record.get("status") != "ok")
        row["estimatedTokens"] += record.get("estimatedTokens") or 0
        row["_durationMs"] += record.get("durationMs") or 0
    for row in tools.values():
        duration = row.pop("_durationMs")
        row["avgTokens"] = round(row["estimatedTokens"] / row["calls"])
        row["avgDurationMs"] = round(duration / row["calls"])

    return {
        "since": since,
        "toolCalls": len(ends),
        "apiCalls": len(api_calls),
        "orphanApiCalls": sum(1 for record in api_calls if not record.get("tool")),
        "clients": dict(Counter((record.get("client") or {}).get("name") or "unknown" for record in ends)),
        "sessions": len({record["sessionId"] for record in records if record.get("sessionId")}),
        "responseBodyChars": sum(len(record.get("responseBody") or "") for record in api_calls),
        "tools": dict(sorted(tools.items(), key=lambda item: -item[1]["estimatedTokens"])),
        "findingCounts": summarize_workflow_efficiency(records)["findingCounts"],
    }
```

Trong `backlog_tool/cli.py`:

```python
# build_parser(), sau block "story"
    telemetry_group = groups.add_parser("telemetry", help="Local telemetry").add_subparsers(dest="action", required=True)
    g = telemetry_group.add_parser("report", help="Summarize telemetry since a date/time prefix")
    g.add_argument("--since", default=datetime.now().date().isoformat(),
                   help="ISO date or datetime prefix, e.g. 2026-09-24 or 2026-09-24T09:00")
```

```python
# run_handler(), trước nhánh cuối
    if group == "telemetry":
        return build_report(read_telemetry(), args.since)
```

Import thêm ở đầu `cli.py`: `from datetime import datetime`, `from backlog_tool.telemetry_report import build_report`, `from backlog_tool.workflow_efficiency import read_telemetry`. Sửa docstring đầu file: nhóm `metrics` → `telemetry`, và dòng "every run is measured into logs/metrics.log" → "every run is traced into logs/telemetry.jsonl".

- [ ] **Step 4: Thêm test parser** vào `tests/test_cli.py` (class `ParserTest`):

```python
    def test_telemetry_report_parses_since(self):
        args = self.parser.parse_args(["telemetry", "report", "--since", "2026-09-24"])
        self.assertEqual(("telemetry", "report", "2026-09-24"), (args.group, args.action, args.since))
        self.assertIsNone(cli.is_dry_run(args))
```

- [ ] **Step 5: Chạy toàn bộ test** — `uv run --extra dev pytest -q` → PASS.
- [ ] **Step 6: Kiểm tra trên log thật** — `uv run backlog-cli --json-full telemetry report --since 2026-09-23`. Kỳ vọng khớp baseline: `toolCalls` 41, `apiCalls` ≥55, `tools.get_bug_context.avgTokens` ≈1215, `findingCounts.apply_without_preview` 8.
- [ ] **Step 7: Commit**

```bash
git add backlog_tool/telemetry_report.py backlog_tool/cli.py tests/test_telemetry_report.py tests/test_cli.py
git commit -m "Add telemetry report CLI for verifying changes on real logs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Phase A — Ngữ cảnh telemetry chính xác

### Task 2: `sessionId`, `surface`, event `server_start` có git sha

**Files:**
- Modify: `backlog_tool/telemetry.py`
- Modify: `backlog_mcp/server.py` (`main`)
- Test: `tests/test_telemetry.py`

**Interfaces:**
- Produces: `telemetry.SESSION_ID: str`, `telemetry.set_surface(surface: str) -> None`, `telemetry.server_version() -> {"version": str|None, "gitSha": str|None, "dirty": bool|None}`, `telemetry.log_server_start(surface: str) -> None`. Mọi record có `sessionId` và `surface` (mặc định `"mcp"`).

- [ ] **Step 1: Viết test fail** (thêm vào `tests/test_telemetry.py`)

```python
def _read(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def test_records_carry_session_and_surface(tmp_path, monkeypatch):
    path = str(tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(telemetry.settings, "TELEMETRY_PATH", path)
    telemetry.begin_tool_trace("get_issue", {"issue_ref": "OOP-1"})
    telemetry.log_telemetry("tool_end", status="ok")
    telemetry.clear_trace()

    records = _read(path)
    assert {r["sessionId"] for r in records} == {telemetry.SESSION_ID}
    assert {r["surface"] for r in records} == {"mcp"}


def test_server_start_records_version_and_pid(tmp_path, monkeypatch):
    path = str(tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(telemetry.settings, "TELEMETRY_PATH", path)
    monkeypatch.setattr(telemetry, "server_version", lambda: {"version": "0.1.0", "gitSha": "abc1234", "dirty": False})
    telemetry.log_server_start("mcp")

    record = _read(path)[0]
    assert record["event"] == "server_start"
    assert record["server"] == {"version": "0.1.0", "gitSha": "abc1234", "dirty": False}
    assert record["pid"] == os.getpid()
    assert telemetry.current_trace_id() is None


def test_server_version_survives_missing_git(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(telemetry.subprocess, "run", boom)
    info = telemetry.server_version()
    assert info["gitSha"] is None and info["dirty"] is None
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_telemetry.py -q` → `KeyError: 'sessionId'` / `AttributeError: server_version`.

- [ ] **Step 3: Implement** trong `backlog_tool/telemetry.py`

```python
import importlib.metadata
import subprocess

SESSION_ID = uuid.uuid4().hex  # one per process; stdio MCP = one client session
_surface: ContextVar[str] = ContextVar("backlog_mcp_surface", default="mcp")


def set_surface(surface: str):
    _surface.set(surface)


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


def log_server_start(surface: str):
    log_telemetry("server_start", surface=surface, pid=os.getpid(), server=server_version())
    clear_trace()
```

Trong `log_telemetry`, thêm vào `record` ngay sau `"client": client_metadata(),`:

```python
            "sessionId": SESSION_ID,
            "surface": _surface.get(),
```

(`fields` được merge sau nên `surface=` truyền tường minh trong `log_server_start` vẫn thắng.)

Trong `backlog_mcp/server.py`:

```python
def main() -> None:
    """Run the workstation-local server over stdio."""
    log_server_start("mcp")
    mcp.run(transport="stdio")
```

và thêm `log_server_start` vào dòng import `from backlog_tool.telemetry import ...`.

- [ ] **Step 4: Chạy toàn bộ test** — `uv run --extra dev pytest -q` → PASS.
- [ ] **Step 5: Commit**

```bash
git add backlog_tool/telemetry.py backlog_mcp/server.py tests/test_telemetry.py
git commit -m "Tag telemetry with session id, surface, and server version

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 3: Event `mutation` cho `resolve_bug` (planHash, trạng thái trước/sau)

**Files:**
- Modify: `workflows/resolve_bug.py` (`build_resolve_bug_payload`, `resolve_bug`)
- Test: `tests/test_bug_workflow.py` (class `BugWorkflowTest`)

**Interfaces:**
- Consumes: `telemetry.log_telemetry` (có sẵn).
- Produces: `bug_workflow.plan_hash(issue_key: str, payload: dict) -> str` (16 hex). `built["planHash"]`. Event telemetry `mutation` với field `mode ("preview"|"apply"), issueKey, planHash, statusBefore, changedFields (list[str]), warnings (list[str])`, và `statusAfter` khi apply.

- [ ] **Step 1: Viết test fail**

```python
    def test_plan_hash_is_stable_and_payload_sensitive(self):
        a = bug_workflow.plan_hash("AQM-1", {"statusId": 4, "comment": "x"})
        b = bug_workflow.plan_hash("AQM-1", {"comment": "x", "statusId": 4})
        c = bug_workflow.plan_hash("AQM-1", {"statusId": 4, "comment": "y"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(16, len(a))

    def test_resolve_logs_mutation_events_linking_preview_and_apply(self):
        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        with mock.patch.object(bug_workflow, "log_telemetry") as log:
            preview = bug_workflow.resolve_bug(
                CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="save validation"
            )
            bug_workflow.resolve_bug(
                CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2), fix_description="save validation"
            )

        (_, first), (_, second) = [(c.args[0], c.kwargs) for c in log.call_args_list]
        self.assertEqual("preview", first["mode"])
        self.assertEqual("apply", second["mode"])
        self.assertEqual(preview["planHash"], first["planHash"])
        self.assertEqual(first["planHash"], second["planHash"])
        self.assertEqual("In Progress", first["statusBefore"])
        self.assertEqual("Resolved", second["statusAfter"])
        self.assertIn("statusId", second["changedFields"])
        self.assertNotIn("statusAfter", first)
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_bug_workflow.py -q -k "plan_hash or mutation_events"` → `AttributeError: plan_hash`.

- [ ] **Step 3: Implement** trong `workflows/resolve_bug.py`

```python
import hashlib
import json

from backlog_tool.telemetry import log_telemetry


def plan_hash(issue_key, payload):
    """Fingerprint of the exact write, so an apply can be matched to its preview."""
    canonical = json.dumps(
        {"issue": issue_key, "payload": payload},
        sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
```

Trong `build_resolve_bug_payload`, trước `return built`:

```python
    built["planHash"] = plan_hash(issue_key, payload)
```

Thay thân `resolve_bug` sau dòng `built = build_resolve_bug_payload(...)`:

```python
    outcome = {
        "issueKey": issue_key,
        "planHash": built["planHash"],
        "statusBefore": built["context"].get("status"),
        "changedFields": sorted(built["payload"].keys()),
        "warnings": built["warnings"],
    }
    if dry_run:
        log_event(
            "info",
            "dry_run",
            command="bug_resolve",
            issue=issue_key,
            project=built["project"],
            payload_keys=",".join(sorted(built["payload"].keys())),
        )
        log_telemetry("mutation", mode="preview", **outcome)
        return {"dryRun": True, **built}
    updated = BacklogClient(config).update_issue(issue_key, built["payload"])
    log_telemetry(
        "mutation",
        mode="apply",
        statusAfter=((updated or {}).get("status") or {}).get("name"),
        **outcome,
    )
    return updated
```

- [ ] **Step 4: Chạy toàn bộ test** — `uv run --extra dev pytest -q` → PASS. (Test `test_resolve_bug_*` hiện có không phụ thuộc số lần gọi `log_telemetry`; conftest đã chuyển log vào tmp.)
- [ ] **Step 5: Commit**

```bash
git add workflows/resolve_bug.py tests/test_bug_workflow.py
git commit -m "Record resolve_bug preview/apply outcome with plan hash and status

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 4: CLI ghi `tool_start`/`tool_end` như MCP

**Files:**
- Modify: `backlog_tool/cli.py` (`execute`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `set_surface`, `begin_tool_trace`, `log_telemetry`, `clear_trace` từ `backlog_tool.telemetry`.
- Produces: `cli.CLI_TOOL_NAMES: dict[str, str]`, `cli.cli_trace_arguments(args) -> dict`. Record CLI có `surface: "cli"` và `tool` = tên tool MCP tương đương (ví dụ `bug:resolve` → `resolve_bug`), `arguments.mode` = `"apply"`/`"preview"` cho lệnh ghi.

- [ ] **Step 1: Viết test fail** (thêm class mới vào `tests/test_cli.py`)

```python
import json as _json
from unittest import mock

from backlog_tool import settings


class CliTelemetryTest(unittest.TestCase):
    def _records(self):
        with open(settings.TELEMETRY_PATH, encoding="utf-8") as handle:
            return [_json.loads(line) for line in handle]

    def test_cli_resolve_is_traced_with_mcp_tool_name(self):
        with mock.patch.object(cli, "load_config", return_value={"base_url": "https://x"}), \
             mock.patch.object(cli, "run_handler", return_value={"dryRun": True, "issue": "OOP-1"}), \
             mock.patch.object(cli, "resolve_project_key_for_issue", return_value="OOP"):
            cli.execute(["bug", "resolve", "OOP-1", "--fix-description", "x"])

        start, end = [r for r in self._records() if r["event"] in ("tool_start", "tool_end")]
        self.assertEqual(("resolve_bug", "cli"), (start["tool"], start["surface"]))
        self.assertEqual("preview", start["arguments"]["mode"])
        self.assertEqual("OOP-1", start["arguments"]["issue_key"])
        self.assertEqual(start["traceId"], end["traceId"])
        self.assertEqual("ok", end["status"])

    def test_cli_error_still_closes_trace(self):
        with mock.patch.object(cli, "load_config", return_value={"base_url": "https://x"}), \
             mock.patch.object(cli, "run_handler", side_effect=RuntimeError("GET /issues/OOP-1 failed with status 404")), \
             mock.patch.object(cli, "resolve_project_key_for_issue", return_value="OOP"):
            with self.assertRaises(RuntimeError):
                cli.execute(["bug", "context", "OOP-1"])

        end = [r for r in self._records() if r["event"] == "tool_end"][-1]
        self.assertEqual(("get_bug_context", "error"), (end["tool"], end["status"]))
        self.assertIn("404", end["error"])
```

Trước khi viết Step 3, kiểm tra tên thuộc tính argparse thật của `bug resolve` (`issue_key`, `fix_description`, `apply`) và `bug context` bằng `uv run backlog-cli bug resolve -h`; nếu khác, sửa test cho khớp tên thật — không đổi parser.

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_cli.py -q -k CliTelemetry` → `FileNotFoundError` (chưa có telemetry) hoặc `ValueError: not enough values to unpack`.

- [ ] **Step 3: Implement** trong `backlog_tool/cli.py`

```python
from backlog_tool.telemetry import begin_tool_trace, clear_trace, log_telemetry, set_surface

# CLI commands recorded under the equivalent MCP tool name so the analyzer
# treats both surfaces as one workflow.
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

Trong `execute`, ngay sau `dry_run = is_dry_run(args)`:

```python
    set_surface("cli")
    tool = CLI_TOOL_NAMES.get(name, name)
    begin_tool_trace(tool, cli_trace_arguments(args))
    trace_started = time.monotonic()
```

và đổi `config = load_config()` thành khối có đóng trace khi lỗi:

```python
    try:
        config = load_config()
    except Exception as error:
        _end_cli_trace("error", trace_started, dry_run, None, error=str(error))
        raise
```

Thêm helper:

```python
def _end_cli_trace(status, started, dry_run, project, *, text="", error=None):
    total = len(text.encode("utf-8"))
    log_telemetry(
        "tool_end",
        status=status,
        durationMs=round((time.monotonic() - started) * 1000, 1),
        project=project,
        dryRun=dry_run,
        totalResponseBytes=total,
        estimatedTokens=round(total / 4),
        error=error,
    )
    clear_trace()
```

Ở nhánh thành công, ngay sau `log_metric(name, len(text...), ...)`: `_end_cli_trace("ok", trace_started, dry_run, project, text=text)`. Ở nhánh `except`, ngay sau `log_metric(name, 0, ...)`: `_end_cli_trace("error", trace_started, dry_run, project, error=str(error))`.

Đổi ví dụ `--issue-key` nếu parser dùng `issue_id` cho `issue get`: analyzer đã nhận cả `issue_id`/`issue_key`/`issue_ref` nên không cần đổi tên.

- [ ] **Step 4: Chạy toàn bộ test** — `uv run --extra dev pytest -q` → PASS.
- [ ] **Step 5: Commit**

```bash
git add backlog_tool/cli.py tests/test_cli.py
git commit -m "Trace CLI commands under their MCP tool names

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 5: Analyzer dùng session, planHash; thêm 2 phát hiện mới

**Files:**
- Modify: `backlog_tool/workflow_efficiency.py` (`build_calls`, `_task_matches_call`, `analyze_task`, `summarize_workflow_efficiency`)
- Test: `tests/test_workflow_efficiency.py`

**Interfaces:**
- Consumes: record `sessionId`, `surface` (Task 2), event `mutation` (Task 3).
- Produces: `call["sessionId"]`, `call["surface"]`, `call["mutation"]` (dict hoặc `None`); `analyze_task(calls, index, preview_hashes=frozenset())`; finding mới `lookup_after_bug_context` (candidate); summary thêm `resolvedAgain: [{"issueKey", "applies", "statusBefore": [...]}]`.

- [ ] **Step 1: Viết test fail** (dùng helper `event`/`tool_trace` có sẵn trong file)

```python
def with_session(records, session):
    return [{**r, "sessionId": session} for r in records]


def mutation(ts, trace, mode, plan_hash, issue="OOP-1", **extra):
    return event(ts, "mutation", trace, "resolve_bug", mode=mode, planHash=plan_hash,
                 issueKey=issue, statusBefore="Open", **extra)


def test_apply_matches_preview_by_plan_hash_across_clients():
    records = tool_trace("2026-09-24T10:00", "p", "resolve_bug", {"issue_key": "OOP-1", "mode": "preview"}, )
    records.append(mutation("2026-09-24T10:00:05+07:00", "p", "preview", "h1"))
    apply = tool_trace("2026-09-24T10:30", "a", "resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    apply = [{**r, "client": {"name": "claude-code", "version": "t", "transport": "stdio"}} for r in apply]
    apply.append(mutation("2026-09-24T10:30:05+07:00", "a", "apply", "h1", statusAfter="Resolved"))

    summary = workflow_efficiency.summarize_workflow_efficiency(records + apply)
    assert "apply_without_preview" not in summary["findingCounts"]


def test_apply_with_unmatched_plan_hash_is_flagged():
    records = tool_trace("2026-09-24T10:00", "a", "resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    records.append(mutation("2026-09-24T10:00:05+07:00", "a", "apply", "zzz"))
    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["findingCounts"]["apply_without_preview"] == 1


def test_different_sessions_of_same_client_are_separate_tasks():
    first = with_session(tool_trace("2026-09-24T10:00", "t1", "get_bug_context", {"issue_key": "OOP-1"}), "s1")
    second = with_session(tool_trace("2026-09-24T10:01", "t2", "get_bug_context", {"issue_key": "OOP-1"}), "s2")
    summary = workflow_efficiency.summarize_workflow_efficiency(first + second)
    assert summary["overview"]["candidateTasks"] == 2
    assert "duplicate_same_call" not in summary["findingCounts"]


def test_get_issue_after_bug_context_is_a_candidate_finding():
    records = tool_trace("2026-09-24T10:00", "t1", "get_bug_context", {"issue_key": "OOP-1"})
    records += tool_trace("2026-09-24T10:01", "t2", "get_issue", {"issue_ref": "OOP-1", "view": "compact"})
    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["findingCounts"]["lookup_after_bug_context"] == 1


def test_resolved_again_lists_issues_applied_twice():
    records = tool_trace("2026-09-24T10:00", "a1", "resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    records.append(mutation("2026-09-24T10:00:05+07:00", "a1", "apply", "h1"))
    records += tool_trace("2026-09-24T17:00", "a2", "resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    records.append(mutation("2026-09-24T17:00:05+07:00", "a2", "apply", "h2"))
    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["resolvedAgain"] == [{"issueKey": "OOP-1", "applies": 2, "statusBefore": ["Open", "Open"]}]


def test_legacy_records_without_session_or_mutation_still_analyze():
    records = tool_trace("2026-09-21T10:00", "a", "resolve_bug", {"issue_key": "OOP-1", "mode": "apply"})
    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["findingCounts"]["apply_without_preview"] == 1
    assert summary["resolvedAgain"] == []
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_workflow_efficiency.py -q` → `KeyError: 'lookup_after_bug_context'` / `KeyError: 'resolvedAgain'`.

- [ ] **Step 3: Implement**

`build_calls`: thêm vào dict mặc định `"sessionId": None, "surface": None, "mutation": None`; trong nhánh `tool_start` thêm:

```python
            call["sessionId"] = record.get("sessionId")
            call["surface"] = record.get("surface")
```

và thêm nhánh:

```python
        elif event == "mutation":
            call["mutation"] = {
                key: record.get(key)
                for key in ("mode", "planHash", "issueKey", "statusBefore", "statusAfter")
            }
```

`_task_matches_call`: thay khối so sánh client bằng:

```python
    first_session, call_session = first.get("sessionId"), call.get("sessionId")
    if first_session and call_session:
        if first_session != call_session:
            return False
    elif (first.get("client") or "unknown") != (call.get("client") or "unknown"):
        return False
```

`analyze_task(calls, index, preview_hashes=frozenset())`: trong vòng `for i, call in enumerate(calls)` thêm:

```python
        if tool == "get_issue" and "get_bug_context" in tools[:i]:
            findings.append(
                _finding(
                    "lookup_after_bug_context",
                    "get_issue followed get_bug_context for the same issue; the bug context may be missing something the client needed.",
                    severity="candidate",
                    calls=[calls[tools[:i].index("get_bug_context")], call],
                )
            )
```

Thay khối `apply_without_preview` bằng:

```python
    for mutation in MUTATION_TOOLS:
        mutation_calls = [call for call in calls if call.get("tool") == mutation]
        applies = [call for call in mutation_calls if (call.get("arguments") or {}).get("mode") == "apply"]
        previews = [call for call in mutation_calls if (call.get("arguments") or {}).get("mode", "preview") != "apply"]
        unmatched = []
        for call in applies:
            plan = (call.get("mutation") or {}).get("planHash")
            if plan:
                if plan not in preview_hashes:
                    unmatched.append(call)
            elif not previews:
                unmatched.append(call)
        if unmatched:
            findings.append(
                _finding(
                    "apply_without_preview",
                    f"{mutation} apply occurred without a matching preview.",
                    severity="warning",
                    calls=unmatched,
                )
            )
```

`summarize_workflow_efficiency`: sau `calls = build_calls(records)`:

```python
    preview_hashes = frozenset(
        call["mutation"]["planHash"]
        for call in calls
        if call.get("mutation") and call["mutation"].get("mode") == "preview" and call["mutation"].get("planHash")
    )
```

truyền `analyze_task(task, index, preview_hashes)`, và thêm vào dict trả về:

```python
        "resolvedAgain": _resolved_again(calls),
```

với:

```python
def _resolved_again(calls):
    applies = defaultdict(list)
    for call in calls:
        outcome = call.get("mutation") or {}
        if call.get("tool") == "resolve_bug" and outcome.get("mode") == "apply":
            applies[outcome.get("issueKey") or call.get("issueKey")].append(outcome.get("statusBefore"))
    return [
        {"issueKey": key, "applies": len(before), "statusBefore": before}
        for key, before in sorted(applies.items())
        if len(before) > 1
    ]
```

Lưu ý: finding `apply_without_preview` giờ đếm theo task (mỗi task tối đa 1 finding) như cũ; test `test_apply_with_unmatched_plan_hash_is_flagged` dựa trên điều đó.

- [ ] **Step 4: Chạy toàn bộ test** — `uv run --extra dev pytest -q` → PASS (gồm các test analyzer cũ).
- [ ] **Step 5: Cập nhật README** mục "Workflow Efficiency Analysis": thêm dòng `get_issue after get_bug_context` và câu "When telemetry has `sessionId`, tasks never span sessions; resolve_bug applies are matched to previews by `planHash` across clients and the CLI." và mục "Telemetry": mô tả `sessionId`, `surface`, `server_start`, event `mutation`.
- [ ] **Step 6: Commit + push phase A**

```bash
git add backlog_tool/workflow_efficiency.py tests/test_workflow_efficiency.py README.md
git commit -m "Use session and plan hash in workflow analysis

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

### Kiểm chứng Phase A (trên log thật)

Restart Claude Code / Antigravity, ghi lại giờ restart (ví dụ `2026-09-24T09:00`), làm việc bình thường ít nhất một buổi (có resolve bug), rồi:

```bash
uv run backlog-cli --json-full telemetry report --since 2026-09-24T09:00
git rev-parse --short HEAD
```

```bash
uv run python - <<'EOF'
import json
from backlog_tool.workflow_efficiency import read_telemetry
since = "2026-09-24T09:00"
rs = [r for r in read_telemetry() if r["ts"] >= since]
print("no sessionId:", sum(1 for r in rs if not r.get("sessionId")))
print("server_start:", [(r["server"]["gitSha"], r["server"]["dirty"]) for r in rs if r["event"] == "server_start"])
ends = {r["traceId"] for r in rs if r["event"] == "tool_end" and r["tool"] == "resolve_bug"}
muts = {r["traceId"] for r in rs if r["event"] == "mutation"}
print("resolve_bug ok without mutation event:", len(ends - muts))
EOF
```

Tiêu chí đạt:
- [ ] `no sessionId` = 0.
- [ ] Mỗi lần restart client có đúng 1 `server_start`, `gitSha` = output `git rev-parse --short HEAD`, `dirty` = False.
- [ ] `orphanApiCalls` = 0 (CLI đã có trace).
- [ ] `resolve_bug ok without mutation event` chỉ gồm call lỗi validate trước khi build payload (thường 0).
- [ ] `apply_without_preview` chỉ còn các apply không có preview cùng `planHash` — đối chiếu tay 1–2 trường hợp bằng `traceIds` trong `backlog://workflow-efficiency`.
- [ ] Nếu có bug bị reopen rồi resolve lại, nó xuất hiện trong `resolvedAgain`.

---

## Phase B — Gọn nguồn log

### Task 6: Chỉ lưu `responseBody` khi cần

**Files:**
- Modify: `backlog_tool/client.py` (`request_json`)
- Test: `tests/test_backlog_client.py`

**Interfaces:**
- Produces: `api_call` luôn có `responseSha256` (16 hex); `responseBody` chỉ có khi response lỗi, method ≠ GET, hoặc env `BACKLOG_MCP_TELEMETRY_BODIES=full`.

- [ ] **Step 1: Viết test fail**

```python
import json
import os
from unittest import mock

import pytest

from backlog_tool import client as client_module, settings


def _response(ok, status, text):
    response = mock.Mock(ok=ok, status_code=status, text=text)
    response.json.return_value = json.loads(text) if ok else {}
    response.raise_for_status.side_effect = None if ok else client_module.requests.HTTPError("x")
    return response


def _api_records():
    with open(settings.TELEMETRY_PATH, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if '"api_call"' in line]


@pytest.mark.parametrize(
    "method, ok, env, keeps_body",
    [("GET", True, None, False), ("GET", False, None, True), ("PATCH", True, None, True), ("GET", True, "full", True)],
)
def test_response_body_retention_policy(monkeypatch, method, ok, env, keeps_body):
    if env:
        monkeypatch.setenv("BACKLOG_MCP_TELEMETRY_BODIES", env)
    else:
        monkeypatch.delenv("BACKLOG_MCP_TELEMETRY_BODIES", raising=False)
    monkeypatch.setattr(client_module, "require_api_key", lambda: "k")
    monkeypatch.setattr(client_module, "api_base_url", lambda config: "https://x/api/v2")
    response = _response(ok, 200 if ok else 404, '{"id": 1}' if ok else '{"errors": []}')
    monkeypatch.setattr(client_module.requests, "request", lambda *a, **k: response)

    try:
        client_module.BacklogClient({}).request_json(method, "/issues/OOP-1")
    except RuntimeError:
        pass

    record = _api_records()[-1]
    assert len(record["responseSha256"]) == 16
    assert ("responseBody" in record) is keeps_body
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `uv run --extra dev pytest tests/test_backlog_client.py -q -k retention` → `KeyError: 'responseSha256'`.

- [ ] **Step 3: Implement** trong `backlog_tool/client.py`

```python
import hashlib
import os


def _keep_response_body(method, ok):
    """Successful reads are reproducible from Backlog; keep bodies only when they explain something."""
    return os.environ.get("BACKLOG_MCP_TELEMETRY_BODIES") == "full" or not ok or method != "GET"
```

Trong `log_telemetry("api_call", ...)` thay `responseBody=response.text,` bằng:

```python
            responseSha256=hashlib.sha256((response.text or "").encode("utf-8")).hexdigest()[:16],
            responseBody=response.text if _keep_response_body(method, response.ok) else None,
```

(`log_telemetry` bỏ field `None`.)

- [ ] **Step 4: Chạy toàn bộ test** — PASS.
- [ ] **Step 5: README** mục Telemetry: thay câu "Request parameters/payloads and Backlog response bodies are retained locally for debugging." bằng: "Request parameters/payloads are retained locally. Backlog response bodies are kept only for errors and writes; successful reads keep a `responseSha256`. Set `BACKLOG_MCP_TELEMETRY_BODIES=full` to keep every body while debugging."
- [ ] **Step 6: Commit**

```bash
git add backlog_tool/client.py tests/test_backlog_client.py README.md
git commit -m "Keep Backlog response bodies only for errors and writes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 7: `telemetry.jsonl` là nguồn duy nhất cho metrics

**Files:**
- Modify: `backlog_tool/telemetry_report.py` (thêm `summarize_metrics`)
- Modify: `backlog_tool/settings.py` (xoá `log_metric`, `read_metrics`, `summarize_metrics`, `METRICS_PATH`)
- Modify: `backlog_mcp/results.py` (bỏ `log_metric`, bỏ `log_event("info","tool_done")`)
- Modify: `backlog_tool/client.py` (`log_response` chỉ ghi khi lỗi)
- Modify: `backlog_tool/cli.py`, `backlog_mcp/server.py` (import `summarize_metrics` từ module mới; bỏ `log_metric`)
- Modify: `tests/conftest.py` (bỏ dòng `METRICS_PATH`)
- Test: `tests/test_metrics.py` (viết lại), `tests/test_backlog_client.py`

**Interfaces:**
- Produces: `telemetry_report.summarize_metrics(records: list[dict] | None = None) -> {"totalRuns": int, "commands": [...]}` — giữ nguyên shape cũ (`command, runs, totalOutputBytes, totalEstimatedTokens, errors, partialWrites, totalTextBytes, totalStructuredBytes, avgOutputBytes, avgEstimatedTokens, avgTextBytes, avgStructuredBytes, errorRate, p95DurationMs`) để `backlog://metrics` không đổi hợp đồng.

- [ ] **Step 1: Viết lại `tests/test_metrics.py` (fail)**

```python
from backlog_tool.telemetry_report import summarize_metrics


def end(tool, status="ok", total=1000, duration=50, text=0, structured=0):
    return {"event": "tool_end", "tool": tool, "status": status, "totalResponseBytes": total,
            "estimatedTokens": round(total / 4), "durationMs": duration,
            "textBytes": text, "structuredBytes": structured, "ts": "2026-09-24T10:00:00+07:00"}


def test_summarize_metrics_from_telemetry_keeps_contract():
    records = [end("get_issue", total=1000), end("get_issue", total=2000, duration=150),
               end("resolve_bug", status="error", total=100, duration=10),
               {"event": "api_call", "tool": "get_issue"}]

    summary = summarize_metrics(records)

    assert summary["totalRuns"] == 3
    rows = {row["command"]: row for row in summary["commands"]}
    assert rows["get_issue"]["runs"] == 2
    assert rows["get_issue"]["avgOutputBytes"] == 1500
    assert rows["get_issue"]["errorRate"] == 0
    assert rows["resolve_bug"]["errorRate"] == 1.0
    assert summary["commands"][0]["command"] == "get_issue"
```

Thêm vào `tests/test_backlog_client.py`:

```python
def test_successful_api_call_is_not_duplicated_in_backlog_log(monkeypatch):
    monkeypatch.setattr(client_module, "require_api_key", lambda: "k")
    monkeypatch.setattr(client_module, "api_base_url", lambda config: "https://x/api/v2")
    monkeypatch.setattr(client_module.requests, "request", lambda *a, **k: _response(True, 200, '{"id": 1}'))
    client_module.BacklogClient({}).request_json("GET", "/issues/OOP-1")
    assert not os.path.exists(settings.LOG_PATH) or '"event": "api"' not in open(settings.LOG_PATH, encoding="utf-8").read()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `ImportError: cannot import name 'summarize_metrics'`.

- [ ] **Step 3: Implement** — thêm vào `backlog_tool/telemetry_report.py`:

```python
from .workflow_efficiency import read_telemetry


def summarize_metrics(records=None):
    records = records if records is not None else read_telemetry()
    ends = [record for record in records if record.get("event") == "tool_end"]
    by_command = {}
    for record in ends:
        command = record.get("tool") or "unknown"
        bucket = by_command.setdefault(command, {
            "command": command, "runs": 0, "totalOutputBytes": 0, "totalEstimatedTokens": 0,
            "errors": 0, "partialWrites": 0, "totalTextBytes": 0, "totalStructuredBytes": 0, "_durations": [],
        })
        bucket["runs"] += 1
        bucket["totalOutputBytes"] += record.get("totalResponseBytes") or 0
        bucket["totalTextBytes"] += record.get("textBytes") or 0
        bucket["totalStructuredBytes"] += record.get("structuredBytes") or 0
        bucket["totalEstimatedTokens"] += record.get("estimatedTokens") or 0
        bucket["errors"] += int(record.get("status") == "error")
        bucket["partialWrites"] += int(record.get("status") == "partial_write")
        if record.get("durationMs") is not None:
            bucket["_durations"].append(record["durationMs"])

    summary = []
    for bucket in by_command.values():
        runs = bucket["runs"]
        durations = sorted(bucket.pop("_durations"))
        bucket["avgOutputBytes"] = round(bucket["totalOutputBytes"] / runs)
        bucket["avgEstimatedTokens"] = round(bucket["totalEstimatedTokens"] / runs)
        bucket["avgTextBytes"] = round(bucket["totalTextBytes"] / runs)
        bucket["avgStructuredBytes"] = round(bucket["totalStructuredBytes"] / runs)
        bucket["errorRate"] = round(bucket["errors"] / runs, 4)
        bucket["p95DurationMs"] = durations[max(0, int(len(durations) * 0.95) - 1)] if durations else None
        summary.append(bucket)
    summary.sort(key=lambda item: item["totalOutputBytes"], reverse=True)
    return {"totalRuns": len(ends), "commands": summary}
```

Rồi:
- `backlog_tool/settings.py`: xoá `METRICS_PATH`, `log_metric`, `read_metrics`, `summarize_metrics`.
- `backlog_mcp/results.py`: xoá import và 3 lời gọi `log_metric(...)`; xoá `log_event("info", "tool_done", ...)` trong `_build_result` (giữ `log_event` cho `tool_error` và `tool_partial_write`).
- `backlog_tool/client.py` `log_response`: chỉ giữ nhánh `else` (lỗi).
- `backlog_tool/cli.py`: xoá import `log_metric`, `summarize_metrics` từ settings và 2 lời gọi `log_metric(...)` (Task 4 đã ghi `tool_end`).
- `backlog_mcp/server.py`: đổi import `summarize_metrics` sang `from backlog_tool.telemetry_report import summarize_metrics`.
- `tests/conftest.py`: xoá dòng `monkeypatch.setattr(settings, "METRICS_PATH", ...)`; `tests/test_mcp_server.py::test_tests_never_write_workstation_logs`: xoá assert `METRICS_PATH`; `test_rejected_tool_arguments_are_recorded_in_metrics_and_telemetry`: thay mock `log_metric` bằng đọc `tool_end` trong `settings.TELEMETRY_PATH` và assert `status == "invalid_arguments"`.
- Tìm sót: `grep -rn "log_metric\|METRICS_PATH\|read_metrics" backlog_mcp backlog_tool workflows tests` → không còn kết quả.

- [ ] **Step 4: Chạy toàn bộ test** — PASS.
- [ ] **Step 5: README** mục "Local State": xoá dòng `metrics.log`, ghi `backlog.log` là "errors and lifecycle events only"; mục resources: `backlog://metrics` "derived from telemetry.jsonl". File `logs/metrics.log` cũ để nguyên trên đĩa (không xoá), ghi chú có thể xoá tay.
- [ ] **Step 6: Commit + push phase B**

```bash
git add -A backlog_tool backlog_mcp tests README.md
git commit -m "Derive metrics from telemetry and stop duplicate log sinks

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

### Kiểm chứng Phase B

Restart client, ghi giờ restart `T`, dùng bình thường, rồi:

```bash
stat -c '%y %s' logs/metrics.log          # mtime phải trước T, size không đổi
grep -c '"event": "api"' logs/backlog.log  # so với trước T: không tăng (trừ lỗi)
uv run backlog-cli --json-full telemetry report --since T
```

Tiêu chí đạt:
- [ ] `logs/metrics.log` không đổi sau `T`.
- [ ] `responseBodyChars` sau `T` chỉ đến từ PATCH/POST và lỗi; GET thành công không có body.
- [ ] Byte telemetry / API call giảm rõ so với baseline (798 KB / 447 record ≈ 1.8 KB/record): đo `wc -c` trên record sau `T` chia số record.
- [ ] `backlog://metrics` (đọc qua MCP client) vẫn trả `totalRuns` + `commands` đúng shape.

---

## Phase C — Giảm payload

### Task 8: `get_bug_context` gọn hơn + attachments + priority

**Files:**
- Modify: `workflows/bug_template.py` (`parse_bug_description` giữ phần preamble, `bug_context`)
- Modify: `workflows/resolve_bug.py` (`get_bug_context` truyền base URL)
- Test: `tests/test_bug_workflow.py`, `tests/test_backlog_api_fixtures.py`

**Interfaces:**
- Produces: `bug_context(issue, base_url="") -> dict`:
  - Bỏ `rawDescription` khi `descriptionMeta.hasTemplateMarkers` là True; giữ khi không có marker.
  - Thêm `descriptionPreamble` khi có chữ trước marker đầu tiên.
  - `customFields` dạng `[{"name", "value"}]` qua `presenter.compact_custom_fields` (bỏ field rỗng).
  - Thêm `priority` (tên) và `attachments: [{"name", "url"}]` (chỉ khi có).
- Không đổi input của tool MCP.

- [ ] **Step 1: Viết test fail** (thêm vào `BugWorkflowTest`)

```python
    def test_bug_context_drops_raw_description_only_when_template_parsed(self):
        templated = {**BUG_ISSUE, "description": "Note from QA\n**Actual:** broken\n**Expected:** works"}
        context = bug_context(templated)
        self.assertNotIn("rawDescription", context)
        self.assertEqual("Note from QA", context["descriptionPreamble"])
        self.assertEqual("broken", context["description"]["actual"])

        free_text = {**BUG_ISSUE, "description": "Button does nothing on click"}
        context = bug_context(free_text)
        self.assertEqual("Button does nothing on click", context["rawDescription"])
        self.assertNotIn("descriptionPreamble", context)

    def test_bug_context_compacts_custom_fields_and_lists_attachments(self):
        issue = {
            **BUG_ISSUE,
            "priority": {"name": "High"},
            "customFields": [
                {"id": 1, "name": "QC Activity", "value": {"id": 5, "name": "Integration Test"}},
                {"id": 2, "name": "Impacted", "value": None},
            ],
            "attachments": [{"id": 77, "name": "shot.png"}],
        }
        context = bug_context(issue, base_url="https://x.backlog.com")
        self.assertEqual([{"name": "QC Activity", "value": "Integration Test"}], context["customFields"])
        self.assertEqual("High", context["priority"])
        self.assertEqual("shot.png", context["attachments"][0]["name"])
        self.assertTrue(context["attachments"][0]["url"].startswith("https://x.backlog.com"))
```

Trong `tests/test_backlog_api_fixtures.py`, đổi `self.assertIn("rawDescription", context)` thành `self.assertNotIn("rawDescription", context)` (fixture có marker — test đó đã assert `description.actual` được parse).

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `KeyError: 'descriptionPreamble'` / `AssertionError` ở `customFields`.

- [ ] **Step 3: Implement** trong `workflows/bug_template.py`

```python
from backlog_tool.presenter import _build_attachment_map, compact_custom_fields


def description_preamble(description):
    text = description or ""
    match = SECTION_PATTERN.search(text)
    return text[: match.start()].strip() if match else ""


def bug_context(issue, base_url=""):
    raw = issue.get("description")
    description = parse_bug_description(raw)
    meta = bug_description_metadata(description)
    context = {
        "issueKey": issue.get("issueKey"),
        "summary": issue.get("summary"),
        "status": (issue.get("status") or {}).get("name"),
        "priority": (issue.get("priority") or {}).get("name"),
        "assignee": compact_user(issue.get("assignee")),
        "createdUser": compact_user(issue.get("createdUser")),
        "startDate": issue.get("startDate"),
        "dueDate": issue.get("dueDate"),
        "estimatedHours": issue.get("estimatedHours"),
        "actualHours": issue.get("actualHours"),
        "description": description,
        "descriptionMeta": meta,
        "customFields": compact_custom_fields(issue.get("customFields")),
    }
    if meta["hasTemplateMarkers"]:
        preamble = description_preamble(raw)
        if preamble:
            context["descriptionPreamble"] = preamble
    else:
        context["rawDescription"] = raw
    attachments = _build_attachment_map(issue.get("attachments"), base_url=base_url)
    if attachments:
        context["attachments"] = [{"name": name, "url": url} for name, url in attachments.items()]
    return context
```

Trong `workflows/resolve_bug.py`:

```python
def get_bug_context(config, issue_key):
    return bug_context(BacklogClient(config).get_issue(issue_key), base_url=view_base_url(config))
```

và thêm `view_base_url` vào import từ `backlog_tool.settings`. Nếu import `backlog_tool.presenter` từ `workflows/bug_template.py` gây vòng import, chuyển import vào trong thân `bug_context`.

- [ ] **Step 4: Chạy toàn bộ test** — PASS. Kiểm tra `resolve_policy`/`detected_roles` không đọc `context["customFields"]` dạng raw: `grep -rn "\[\"context\"\]" workflows backlog_tool backlog_mcp` → chỉ có `built["context"].get("status")` (Task 3).
- [ ] **Step 5: Đo offline trên response cũ** (log trước Phase B còn body):

```bash
uv run python - <<'EOF'
import json
from workflows.bug_template import bug_context
seen = set()
for line in open("logs/telemetry.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r.get("event") == "api_call" and r.get("method") == "GET" and r.get("responseBody") and r["path"].startswith("/issues/OOP-"):
        key = r["path"].split("/")[2]
        if key in seen:
            continue
        seen.add(key)
        size = len(json.dumps(bug_context(json.loads(r["responseBody"])), ensure_ascii=False).encode())
        print(key, size)
EOF
```

Kỳ vọng: đa số bug ≤ 2.8 KB (baseline 3.6–5.4 KB, OOP-12777 10 KB).
- [ ] **Step 6: Commit**

```bash
git add workflows/bug_template.py workflows/resolve_bug.py tests/test_bug_workflow.py tests/test_backlog_api_fixtures.py
git commit -m "Slim get_bug_context and include attachments and priority

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 9: `get_my_open_bugs` không trả description

**Files:**
- Modify: `backlog_tool/presenter.py` (`compact_issue` hỗ trợ `view="list"`)
- Modify: `backlog_mcp/server.py` (`get_my_open_bugs` dùng `view="list"`; docstring nói rõ dùng `get_bug_context` để xem chi tiết)
- Test: `tests/test_cli.py` (presenter), `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `compact_issue(issue, view="list")` = như `compact` nhưng không có `description`.

- [ ] **Step 1: Viết test fail**

Trong `tests/test_cli.py` (dùng `RAW_ISSUE` có sẵn):

```python
class ListViewTest(unittest.TestCase):
    def test_list_view_omits_description(self):
        issue = {**RAW_ISSUE, "description": "long text"}
        self.assertEqual("long text", presenter.compact_issue(issue, view="compact")["description"])
        listed = presenter.compact_issue(issue, view="list")
        self.assertNotIn("description", listed)
        self.assertEqual("AQM-1", listed["issueKey"])
```

Trong `tests/test_mcp_server.py`:

```python
def test_get_my_open_bugs_returns_list_view_without_description():
    issue = {"issueKey": "OOP-1", "summary": "S", "description": "long", "status": {"name": "Open"}}
    with mock.patch("backlog_mcp.server.get_config_instance", return_value={"base_url": "https://x"}), \
         mock.patch("backlog_mcp.server.bug_workflow.my_open_bugs_raw", return_value=[issue]):
        result = server.get_my_open_bugs(project_key="OOP")
    assert "description" not in result.structuredContent["data"]["bugs"][0]
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL** — `AssertionError: 'description' in ...`.
- [ ] **Step 3: Implement** — trong `compact_issue`, trước `return result`:

```python
    if view == "list":
        result.pop("description", None)
```

Trong `get_my_open_bugs` (server): `presenter.compact_issue(item, view="list", base_url=base_url)`. Thêm vào docstring: `Returns summaries only; call get_bug_context for a bug's description and evidence.`

- [ ] **Step 4: Chạy toàn bộ test** — PASS (test snapshot docstring/instructions trong `test_mcp_server.py` có thể cần cập nhật chuỗi mong đợi — chỉ sửa chuỗi, không nới assertion).
- [ ] **Step 5: Commit + push phase C**

```bash
git add backlog_tool/presenter.py backlog_mcp/server.py tests/test_cli.py tests/test_mcp_server.py
git commit -m "Return bug summaries without descriptions from get_my_open_bugs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin main
```

### Kiểm chứng Phase C

Restart client, ghi giờ `T`, làm việc bình thường ≥1 ngày có xử lý bug, rồi `uv run backlog-cli --json-full telemetry report --since T`.

| Chỉ số | Baseline | Mục tiêu |
|---|---|---|
| `tools.get_bug_context.avgTokens` | ~1215 | ≤ 750 |
| `get_my_open_bugs` token / bug (`estimatedTokens / itemCount` trong `tool_end`) | ~681 | ≤ 250 |
| `findingCounts.lookup_after_bug_context` / số `get_bug_context` | 4 / 10 | giảm rõ (mục tiêu ≤ 1 / 10) |
| Model có hỏi lại / gọi `get_issue` để lấy description sau `get_my_open_bugs`? | — | đọc `tools` + timeline; nếu có, cân nhắc thêm `descriptionPreview` ngắn |

---

## Quyết định còn mở (không nằm trong plan)

- `resolve_bug` apply không preview (8/15 ngày 2026-09-23): (a) server bắt buộc có preview cùng `planHash` trong N phút, hoặc (b) chấp nhận và hạ `apply_without_preview` xuống `candidate`. Sau Phase A, `planHash` cho phép làm (a) chính xác — quyết định sau khi xem số liệu Phase A.
