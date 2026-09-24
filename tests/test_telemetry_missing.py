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
