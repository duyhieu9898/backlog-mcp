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


def test_load_calls_skips_malformed_and_missing_trace_id():
    import os
    import json
    from backlog_tool import settings

    # Create a calls.jsonl with garbage line + line without traceId + valid call
    calls_path = os.path.join(settings.LOG_DIR, "calls.jsonl")
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    # Start a real call to have a valid row
    make_call("get_bug_context", {"issue_key": "OOP-1"})

    # Append garbage and missing-traceId lines to the file
    with open(calls_path, "a", encoding="utf-8") as f:
        f.write("this is not valid json\n")
        f.write(json.dumps({"ts": "2026-01-01T00:00:00Z", "tool": "orphan", "status": "ok"}) + "\n")

    calls = load_calls()
    # Should have only 1 call (the valid one from make_call), not 3
    assert len(calls) == 1
    assert calls[0].tool == "get_bug_context"


def test_load_calls_reads_rotated_backup_files():
    import os
    import json
    from backlog_tool import settings

    calls_path = os.path.join(settings.LOG_DIR, "calls.jsonl")
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    # Create a call in calls.jsonl.1 (rotated backup)
    backup_path = f"{calls_path}.1"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "traceId": "trace-backup",
            "ts": "2026-01-01T00:00:00.000Z",
            "tool": "backup_tool",
            "status": "ok",
        }) + "\n")

    # Create another call in calls.jsonl
    with open(calls_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "traceId": "trace-current",
            "ts": "2026-01-02T00:00:00.000Z",
            "tool": "current_tool",
            "status": "ok",
        }) + "\n")

    calls = load_calls()
    assert len(calls) == 2
    # Should be sorted by ts: backup first, then current
    assert calls[0].tool == "backup_tool"
    assert calls[1].tool == "current_tool"
