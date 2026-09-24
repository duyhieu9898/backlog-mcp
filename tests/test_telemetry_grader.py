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
    good = grade(expect, Flow("r", [call("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"})]))
    assert good["pass"] is True and good["extraCalls"] == []

    two = grade(expect, Flow("r", [
        call("resolve_bug", {"issue_key": "OOP-912762", "mode": "preview"}),
        call("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"}),
    ]))
    assert two["pass"] is False and two["extraCalls"] == ["resolve_bug"]


def test_forbidden_and_arg_errors_fail():
    expect = scenario("resolve_fixed")["expect"]
    result = grade(expect, Flow("r", [
        call("get_bug_context", {"issue_key": "OOP-912762"}),
        call("resolve_bug", {"issueKey": "OOP-912762"}, status="invalid_arguments", errors=[{"kind": "arg_error", "unknown": ["issueKey"]}]),
        call("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"}),
    ]))
    assert result["pass"] is False
    assert result["forbiddenHits"] == ["get_bug_context"]
    assert result["argErrors"] == [{"tool": "resolve_bug", "unknown": ["issueKey"]}]


def test_multi_any_order_and_final_answer():
    expect = scenario("resolve_multi")["expect"]
    flow = Flow("r", [
        call("resolve_bug", {"issue_key": "OOP-912773", "mode": "apply"}),
        call("resolve_bug", {"issue_key": "OOP-912774", "mode": "apply"}),
    ])
    assert grade(expect, flow)["pass"] is True

    warn = scenario("resolve_warning")["expect"]
    flow = Flow("r", [call("resolve_bug", {"issue_key": "OOP-912749", "mode": "apply"})])
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


def test_unknown_tool_calls_fail_as_extra():
    expect = scenario("resolve_fixed")["expect"]
    result = grade(expect, Flow("r", [
        call("resolve_bugs", {"issue_key": "OOP-912762"}, status="rejected"),
        call("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"}),
    ]))
    assert result["pass"] is False
    assert "unknown tool calls: ['resolve_bugs']" in result["reasons"]
    assert "resolve_bugs" in result["extraCalls"]


def test_invalid_arguments_still_excluded_from_matching():
    expect = scenario("resolve_fixed")["expect"]
    result = grade(expect, Flow("r", [
        call("resolve_bug", {"issueKey": "OOP-912762"}, status="invalid_arguments"),
        call("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"}),
    ]))
    assert result["pass"] is True and result["extraCalls"] == []


def test_missing_final_answer_fails_only_when_required():
    warn = scenario("resolve_warning")["expect"]
    flow = Flow("r", [call("resolve_bug", {"issue_key": "OOP-912749", "mode": "apply"})])
    skipped = grade(warn, flow)
    assert skipped["pass"] is True and skipped["finalAnswerCheck"] == {"skipped": "no final answer"}
    required = grade(warn, flow, final_answer=None, require_final_answer=True)
    assert required["pass"] is False and "final answer missing" in required["reasons"]
