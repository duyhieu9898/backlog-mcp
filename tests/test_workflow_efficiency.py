from backlog_tool import workflow_efficiency


def event(ts, event_name, trace_id, tool, *, arguments=None, client="codex", **extra):
    record = {
        "schemaVersion": 2,
        "ts": ts,
        "event": event_name,
        "traceId": trace_id,
        "tool": tool,
        "client": {"name": client, "version": "test", "transport": "stdio"},
    }
    if arguments is not None:
        record["arguments"] = arguments
    record.update(extra)
    return record


def tool_trace(ts_prefix, trace_id, tool, arguments, *, status="ok", bytes_=400, api_calls=1):
    records = [
        event(f"{ts_prefix}:00+07:00", "tool_start", trace_id, tool, arguments=arguments),
    ]
    for index in range(api_calls):
        records.append(
            event(
                f"{ts_prefix}:0{index + 1}+07:00",
                "api_call",
                trace_id,
                tool,
                durationMs=10,
                responseBytes=100,
            )
        )
    records.append(
        event(
            f"{ts_prefix}:09+07:00",
            "tool_end",
            trace_id,
            tool,
            status=status,
            durationMs=20,
            totalResponseBytes=bytes_,
            estimatedTokens=round(bytes_ / 4),
        )
    )
    return records


def test_analyzer_detects_redundant_bug_lookup_and_duplicate_call():
    records = []
    records += tool_trace(
        "2026-09-21T10:00",
        "t1",
        "get_issue",
        {"issue_id": "OOP-12754", "view": "compact"},
    )
    records += tool_trace(
        "2026-09-21T10:01",
        "t2",
        "get_bug_context",
        {"issue_key": "OOP-12754"},
    )
    records += tool_trace(
        "2026-09-21T10:02",
        "t3",
        "get_bug_context",
        {"issue_key": "OOP-12754"},
    )

    summary = workflow_efficiency.summarize_workflow_efficiency(records)

    assert summary["overview"]["candidateTasks"] == 1
    task = summary["tasks"][0]
    codes = [item["code"] for item in task["findings"]]
    assert "generic_lookup_before_bug_context" in codes
    assert "duplicate_same_call" in codes
    assert task["mcpCalls"] == 3
    assert task["apiCalls"] == 3
    assert task["totalResponseBytes"] == 1200


def test_analyzer_flags_diagnostic_prestep_and_apply_without_preview():
    records = []
    records += tool_trace(
        "2026-09-21T11:00",
        "t1",
        "get_bug_rules",
        {"project_key": "OOP"},
        api_calls=0,
    )
    records += tool_trace(
        "2026-09-21T11:01",
        "t2",
        "resolve_bug",
        {"issue_key": "OOP-12754", "mode": "apply"},
        api_calls=2,
    )

    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["overview"]["candidateTasks"] == 1
    findings = summary["tasks"][0]["findings"]
    by_code = {item["code"]: item for item in findings}
    assert by_code["diagnostic_prestep_before_resolve"]["severity"] == "candidate"
    assert by_code["apply_without_preview"]["severity"] == "warning"


def test_analyzer_recognizes_preview_apply_as_non_duplicate():
    records = []
    records += tool_trace(
        "2026-09-21T12:00",
        "t1",
        "resolve_bug",
        {"issue_key": "OOP-12754", "mode": "preview"},
    )
    records += tool_trace(
        "2026-09-21T12:01",
        "t2",
        "resolve_bug",
        {"issue_key": "OOP-12754", "mode": "apply"},
    )

    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    codes = [item["code"] for item in summary["tasks"][0]["findings"]]
    assert "duplicate_same_call" not in codes
    assert "apply_without_preview" not in codes


def test_analyzer_marks_split_status_path_as_candidate():
    records = []
    records += tool_trace(
        "2026-09-21T13:00",
        "t1",
        "get_my_work_overview",
        {"project_key": "OOP"},
    )
    records += tool_trace(
        "2026-09-21T13:01",
        "t2",
        "get_my_open_bugs",
        {"project_key": "OOP"},
    )

    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    finding = next(
        item
        for item in summary["tasks"][0]["findings"]
        if item["code"] == "split_personal_status_path"
    )
    assert finding["severity"] == "candidate"


def test_analyzer_keeps_different_clients_separate():
    records = []
    records += tool_trace(
        "2026-09-21T14:00",
        "c1",
        "get_my_project_status",
        {"project_key": "OOP"},
    )
    other = tool_trace(
        "2026-09-21T14:01",
        "a1",
        "get_my_project_status",
        {"project_key": "OOP"},
    )
    for record in other:
        record["client"]["name"] = "claude"
    records += other

    summary = workflow_efficiency.summarize_workflow_efficiency(records)
    assert summary["overview"]["candidateTasks"] == 2
    assert [item["client"] for item in summary["clients"]] == ["claude", "codex"]
