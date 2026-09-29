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
    make("get_issue", {"issue_key": "OOP-912762"})
    make("resolve_bug", {"issue_key": "OOP-912762", "mode": "apply"})
    telemetry.set_eval_tags(None, None)
    make("get_issue", {"issue_ref": "OOP-5"}, status="error", size=9000)

    report = report_from_logs()
    [eval_flow] = [f for f in report["flows"] if f["flowId"] == "run-1"]
    assert eval_flow["grade"]["pass"] is False
    assert eval_flow["grade"]["forbiddenHits"] == ["get_issue"]
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


def test_report_from_claude_compares_since_as_instants(tmp_path):
    import json

    from backlog_tool.telemetry_report import report_from_claude

    path = tmp_path / "projects" / "-home-u-proj" / "s.jsonl"
    path.parent.mkdir(parents=True)
    with open(path, "w", encoding="utf-8") as handle:
        for ts, prompt in (("2026-01-10T02:30:00Z", "backlog before"), ("2026-01-10T03:30:00Z", "backlog after")):
            handle.write(json.dumps({"type": "user", "timestamp": ts, "cwd": "/home/u/proj", "message": {"role": "user", "content": prompt}}) + "\n")
    report = report_from_claude(since="2026-01-10T10:00:00+07:00", root=str(tmp_path / "projects"), log_dir=str(tmp_path / "logs"))
    assert [f["prompt"] for f in report["flows"]] == ["backlog after"]


def call_on(tool, issue_key, mode=None, status="ok", warnings=None):
    from backlog_tool.telemetry_store import Call

    arguments = {"issue_key": issue_key, **({"mode": mode} if mode else {})}
    return Call(
        trace_id=f"{tool}-{mode}-{status}", ts="", tool=tool, arguments=arguments, status=status,
        duration_ms=1, api_calls=1, response_bytes=1, est_tokens=1, client="c", session_id="s",
        surface="mcp", run_id=None, scenario=None, issue_key=issue_key, project_key="OOP",
        result={"ok": True, "data": {"warnings": warnings or []}},
    )


def test_issue_flags_from_real_usage_patterns():
    from backlog_tool.telemetry_report import issue_flags

    # OOP-12789: resolved, a follow-up resolve refused, then corrections as comments.
    assert issue_flags([
        call_on("resolve_bug", "OOP-12789", "apply"),
        call_on("resolve_bug", "OOP-12789", "apply", status="error"),
        call_on("update_issue", "OOP-12789", "apply"),
    ]) == ["refused", "rework"]
    # OOP-12816 from a client with a stale schema: preview twice, then apply.
    assert issue_flags([
        call_on("get_issue", "OOP-12816"),
        call_on("resolve_bug", "OOP-12816", "preview"),
        call_on("resolve_bug", "OOP-12816", "preview"),
        call_on("resolve_bug", "OOP-12816", "apply"),
    ]) == ["preview-then-apply"]
    # OOP-12798: a prefilled Corrective Action was kept.
    kept = ["Kept the existing Corrective Action 'x' because no fix_description was given; ..."]
    assert issue_flags([call_on("resolve_bug", "OOP-12798", "apply", warnings=kept)]) == ["kept-corrective-action"]
    assert issue_flags([call_on("get_issue", "OOP-1"), call_on("resolve_bug", "OOP-1", "apply")]) == []


def test_report_lists_issue_timelines():
    make("get_issue", {"issue_key": "OOP-7"})
    make("resolve_bug", {"issue_key": "OOP-7", "mode": "preview"})
    make("resolve_bug", {"issue_key": "OOP-7", "mode": "apply"})

    report = report_from_logs()
    [row] = report["issues"]
    assert row["issue"] == "OOP-7"
    assert row["steps"] == ["get_issue", "resolve_bug(preview)", "resolve_bug"]
    assert row["flags"] == ["preview-then-apply"]
    assert report["issueFlags"] == {"preview-then-apply": 1}
