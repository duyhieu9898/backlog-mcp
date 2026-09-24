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


def test_rejected_call_writes_unknown_tool_error():
    telemetry.start_call("get_isssue", {"issue_ref": "OOP-1"})
    telemetry.finish_call("rejected", error="Unknown tool: get_isssue")
    [error] = read("errors")
    assert error["kind"] == "unknown_tool"
    assert error["message"] == "Unknown tool: get_isssue"
    assert error["tool"] == "get_isssue"
    assert read("calls")[0]["status"] == "rejected"


def test_finish_call_never_raises_and_clears_context(monkeypatch, capsys):
    def broken(value):
        raise RuntimeError("cannot serialize")

    telemetry.start_call("resolve_bug", {"issue_key": "OOP-1"})
    monkeypatch.setattr(telemetry, "_jsonable", broken)
    trace = telemetry.finish_call("ok", result={"ok": True}, text="{}")
    assert telemetry.current_trace_id() is None
    assert trace is None or isinstance(trace, str)
