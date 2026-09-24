import json

import pytest

from backlog_tool import settings, telemetry
from backlog_tool.telemetry_grader import load_scenarios, render_scenario
from evals.agents import AgentTrace
from evals.run import grade_run, prepare_workspace, run_one, write_summary


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
    telemetry.start_call("resolve_bug", {"issue_key": "OOP-912749", "mode": "apply"})
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


def test_run_one_removes_markers_from_supplied_workspace_on_error(tmp_path, monkeypatch):
    import evals.run as run_module

    def boom(*args, **kwargs):
        raise FileNotFoundError("agent binary not found")

    monkeypatch.setattr(run_module.subprocess, "run", boom)
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(FileNotFoundError):
        run_one("claude", "opus", scenario("open_bugs"), 0, 30, workspace=str(ws), source="synthetic")

    assert not (ws / ".backlog-eval.json").exists()
    assert not (ws / ".backlog-project.json").exists()


def test_write_summary(tmp_path):
    rows = [{"scenario": "open_bugs", "pass": True}, {"scenario": "open_bugs", "pass": False, "reasons": ["extra calls: ['get_issues']"]}]
    (tmp_path / "claude-opus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    text = (tmp_path / "SUMMARY.md").read_text()
    assert "| open_bugs | 1/2 |" in text and "claude-opus" in text and "extra calls ×1" in text
