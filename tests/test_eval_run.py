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
    telemetry.log_session_start(backend="fake")
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


def _completed(stdout=""):
    import subprocess

    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_agent_env_strips_backlog_variables(tmp_path, monkeypatch):
    from evals.run import agent_env

    monkeypatch.setenv("BACKLOG_API_KEY", "real-key")
    monkeypatch.setenv("BACKLOG_BASE_URL", "https://real.backlog.com")
    monkeypatch.setenv("BACKLOG_MCP_LOG_DIR", "/real/logs")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = agent_env(tmp_path)
    assert [k for k in env if k.startswith("BACKLOG_")] == ["BACKLOG_WORKSPACE_PATH"]
    assert env["BACKLOG_WORKSPACE_PATH"] == str(tmp_path)
    assert env["PATH"] == "/usr/bin"


def test_run_one_passes_scrubbed_env_to_agent(tmp_path, monkeypatch):
    import evals.run as run_module

    monkeypatch.setenv("BACKLOG_API_KEY", "real-key")
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs, command=command)
        return _completed()

    monkeypatch.setattr(run_module.subprocess, "run", fake_run)
    run_one("claude", "opus", scenario("open_bugs"), 0, 30, source="synthetic")
    assert "BACKLOG_API_KEY" not in seen["env"]
    assert seen["env"]["BACKLOG_WORKSPACE_PATH"] == str(seen["cwd"])


def _session_row(log_dir, **fields):
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "session_start", **fields}) + "\n")


def test_grade_run_flags_isolation_failure_without_fake_session(tmp_path):
    log_dir = tmp_path / "logs"
    _session_row(log_dir, backend="real", runId="run-1")
    trace = AgentTrace(final_answer="ok", raw_ok=True)
    result = grade_run(scenario("open_bugs"), trace, log_dir, "run-1")
    assert result["isolationFailed"] is True and result["pass"] is False
    assert "isolation: server did not run on the fake backend" in result["reasons"]


def test_grade_run_accepts_fake_session(tmp_path):
    log_dir = tmp_path / "logs"
    _session_row(log_dir, backend="fake", runId="run-1")
    trace = AgentTrace(final_answer="ok", raw_ok=True)
    result = grade_run(scenario("open_bugs"), trace, log_dir, "run-1")
    assert "isolationFailed" not in result


def test_main_stops_batch_after_isolation_failure(tmp_path, monkeypatch, capsys):
    import evals.run as run_module

    calls = []

    def fake_run_one(*args, **kwargs):
        calls.append(args)
        return {"scenario": "open_bugs", "pass": False, "isolationFailed": True,
                "reasons": ["isolation: server did not run on the fake backend"]}

    monkeypatch.setattr(run_module, "run_one", fake_run_one)
    monkeypatch.setattr(run_module, "config_fingerprint", lambda agent: {})
    monkeypatch.setattr(run_module, "RESULTS_ROOT", tmp_path)
    code = run_module.main(["--agent", "claude", "--model", "opus", "--scenario", "open_bugs", "--runs", "3"])
    assert len(calls) == 1 and code == 2
    assert "isolation" in capsys.readouterr().out.lower()


def test_run_one_uses_strict_mcp_config_outside_workspace(tmp_path, monkeypatch):
    import evals.run as run_module

    seen = {}

    def fake_run(command, **kwargs):
        index = command.index("--mcp-config")
        seen["cwd"] = kwargs["cwd"]
        seen["path"] = command[index + 1]
        seen["config"] = json.loads(open(command[index + 1], encoding="utf-8").read())
        seen["command"] = command
        return _completed()

    monkeypatch.setattr(run_module.subprocess, "run", fake_run)
    run_one("claude", "opus", scenario("open_bugs"), 0, 30, source="synthetic")
    assert "--strict-mcp-config" in seen["command"]
    server = seen["config"]["mcpServers"]["backlog"]
    assert server["command"] == "uv"
    assert server["args"] == ["--project", settings.MCP_ROOT, "run", "backlog-mcp-server"]
    assert not seen["path"].startswith(str(seen["cwd"]))


def test_run_one_restores_existing_project_file_after_error(tmp_path, monkeypatch):
    import evals.run as run_module

    def boom(*args, **kwargs):
        raise FileNotFoundError("agent binary not found")

    monkeypatch.setattr(run_module.subprocess, "run", boom)
    ws = tmp_path / "ws"
    ws.mkdir()
    original = b'{"project_key": "NLN"}'
    (ws / ".backlog-project.json").write_bytes(original)

    with pytest.raises(FileNotFoundError):
        run_one("claude", "opus", scenario("open_bugs"), 0, 30, workspace=str(ws), source="synthetic")

    assert (ws / ".backlog-project.json").read_bytes() == original
    assert not (ws / ".backlog-eval.json").exists()


def test_run_one_restores_existing_project_file_after_normal_run(tmp_path, monkeypatch):
    import evals.run as run_module

    monkeypatch.setattr(run_module.subprocess, "run", lambda *a, **k: _completed())
    ws = tmp_path / "ws"
    ws.mkdir()
    original = b'{"project_key": "NLN"}'
    (ws / ".backlog-project.json").write_bytes(original)

    run_one("claude", "opus", scenario("open_bugs"), 0, 30, workspace=str(ws), source="synthetic")

    assert (ws / ".backlog-project.json").read_bytes() == original
    assert not (ws / ".backlog-eval.json").exists()
