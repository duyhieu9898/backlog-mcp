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
