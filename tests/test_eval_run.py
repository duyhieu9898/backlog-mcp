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

    monkeypatch.setattr(run_module, "run_agent", boom)
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(FileNotFoundError):
        run_one("claude", "opus", scenario("open_bugs"), 0, 30, workspace=str(ws), source="synthetic")

    assert not (ws / ".backlog-eval.json").exists()
    assert not (ws / ".backlog-project.json").exists()


def test_write_summary(tmp_path):
    rows = [
        {"scenario": "open_bugs", "pass": True, "estTokens": 100, "wallClockMs": 4000},
        {"scenario": "open_bugs", "pass": False, "reasons": ["extra calls: ['get_issues']"], "estTokens": 300, "wallClockMs": 9000},
        {"scenario": "open_bugs", "pass": True, "estTokens": 200, "wallClockMs": None},
    ]
    (tmp_path / "claude-opus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    text = (tmp_path / "SUMMARY.md").read_text()
    assert "| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |" in text
    assert "| open_bugs | 2/3 | 0 | 0 | 200 | 6500 |" in text and "claude-opus" in text and "extra calls ×1" in text


def _completed(stdout=""):
    from evals.run import AgentProcess

    return AgentProcess(lines=stdout.splitlines(), stderr_tail="", timed_out=False)


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

    def fake_run(command, cwd, env, timeout_s):
        seen.update(cwd=cwd, env=env, command=command)
        return _completed()

    monkeypatch.setattr(run_module, "run_agent", fake_run)
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

    def fake_run(command, cwd, env, timeout_s):
        index = command.index("--mcp-config")
        seen["cwd"] = cwd
        seen["path"] = command[index + 1]
        seen["config"] = json.loads(open(command[index + 1], encoding="utf-8").read())
        seen["command"] = command
        return _completed()

    monkeypatch.setattr(run_module, "run_agent", fake_run)
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

    monkeypatch.setattr(run_module, "run_agent", boom)
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

    monkeypatch.setattr(run_module, "run_agent", lambda *a, **k: _completed())
    ws = tmp_path / "ws"
    ws.mkdir()
    original = b'{"project_key": "NLN"}'
    (ws / ".backlog-project.json").write_bytes(original)

    run_one("claude", "opus", scenario("open_bugs"), 0, 30, workspace=str(ws), source="synthetic")

    assert (ws / ".backlog-project.json").read_bytes() == original
    assert not (ws / ".backlog-eval.json").exists()


def test_grade_run_requires_final_answer(tmp_path):
    log_dir = tmp_path / "logs"
    telemetry.set_eval_tags("run-2", "resolve_warning")
    telemetry.log_session_start(backend="fake")
    telemetry.start_call("resolve_bug", {"issue_key": "OOP-912749", "mode": "apply"})
    telemetry.finish_call("ok", result={"ok": True}, text="{}", response_bytes=300)
    telemetry.set_eval_tags(None, None)
    result = grade_run(scenario("resolve_warning"), AgentTrace(final_answer=None, raw_ok=False), tmp_path / "logs", "run-2")
    assert result["pass"] is False and "final answer missing" in result["reasons"]


def test_run_agent_stops_at_result_event(tmp_path):
    import sys
    import time

    from evals.run import run_agent

    script = (
        "import sys, time\n"
        "print('{\"event\":\"init\"}', flush=True)\n"
        "print('{\"event\":\"result\",\"result\":{\"status\":\"SUCCESS\"}}', flush=True)\n"
        "time.sleep(60)\n"
    )
    started = time.monotonic()
    proc = run_agent([sys.executable, "-c", script], cwd=tmp_path, env=None, timeout_s=50)
    assert time.monotonic() - started < 15
    assert len(proc.lines) == 2 and proc.timed_out is False


def test_run_agent_times_out(tmp_path):
    import sys

    from evals.run import run_agent

    script = "import sys, time\nprint('partial', flush=True)\nsys.stderr.write('boom'); sys.stderr.flush()\ntime.sleep(60)\n"
    proc = run_agent([sys.executable, "-c", script], cwd=tmp_path, env=None, timeout_s=1, grace_s=1)
    assert proc.timed_out is True and proc.lines == ["partial"] and "boom" in proc.stderr_tail


@pytest.mark.parametrize("stderr, timed_out, ok, expected", [
    ("Eligibility check failed: UNAVAILABLE (code 503): The service is currently unavailable.", False, False, "service_unavailable"),
    ("connecting to sandbox server: read: connection reset by peer", False, False, "sandbox"),
    ("", True, False, "timeout"),
    ("", False, False, "agent_failed"),
    ("", False, True, None),
])
def test_classify_env_error(stderr, timed_out, ok, expected):
    from evals.run import AgentProcess, classify_env_error

    trace = AgentTrace(raw_ok=ok)
    assert classify_env_error(AgentProcess(lines=[], stderr_tail=stderr, timed_out=timed_out), trace) == expected


def test_classify_env_error_scans_stdout_for_service_errors():
    from evals.run import AgentProcess, classify_env_error

    proc = AgentProcess(lines=["error: UNAVAILABLE (code 503)"], stderr_tail="", timed_out=False)
    assert classify_env_error(proc, AgentTrace(raw_ok=False)) == "service_unavailable"


def test_write_summary_counts_env_errors(tmp_path):
    rows = [
        {"scenario": "open_bugs", "pass": False, "envError": "service_unavailable", "reasons": ["missing expected call x"]},
        {"scenario": "open_bugs", "pass": True},
    ]
    (tmp_path / "agy-flash.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    text = (tmp_path / "SUMMARY.md").read_text()
    assert "| open_bugs | 1/2 | 1 | 0 | - | - |" in text
    assert "Lỗi môi trường: service_unavailable ×1" in text
    assert "missing expected call ×1" not in text


AGY_LIST = """NAME                    TYPE   STATUS    COMMAND/URL
backlog                 stdio  enabled   uv --project /x run backlog-mcp-server
chrome-devtools-mcp     stdio  enabled   npx -y chrome-devtools-mcp@latest --autoConnect
morph-mcp               stdio  disabled  npx morph
website-design-systems  stdio  enabled   npx -y website-design-systems-mcp
"""


def test_agy_other_mcp_servers_disabled_and_restored(monkeypatch):
    import subprocess

    import evals.run as run_module

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        stdout = AGY_LIST if command[:3] == ["agy", "mcp", "list"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(run_module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        with run_module.agy_mcp_isolated():
            assert calls[1:] == [["agy", "mcp", "disable", "chrome-devtools-mcp"],
                                 ["agy", "mcp", "disable", "website-design-systems"]]
            raise RuntimeError("batch crashed")
    assert calls[3:] == [["agy", "mcp", "enable", "chrome-devtools-mcp"],
                         ["agy", "mcp", "enable", "website-design-systems"]]


def test_write_summary_counts_runs_with_arg_errors(tmp_path):
    rows = [{"scenario": "resolve_fixed", "pass": False, "argErrors": [{"tool": "resolve_bug"}], "reasons": ["argument errors: x"]},
            {"scenario": "resolve_fixed", "pass": True, "argErrors": []}]
    (tmp_path / "claude-opus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_summary(tmp_path)
    assert "| resolve_fixed | 1/2 | 0 | 1 | - | - |" in (tmp_path / "SUMMARY.md").read_text()


def test_run_one_builds_codex_command_for_the_eval_workspace(tmp_path, monkeypatch):
    import evals.run as run_module

    seen = {}

    def fake_run(command, cwd, env, timeout_s):
        seen.update(command=command, cwd=cwd, env=env)
        return _completed()

    monkeypatch.setattr(run_module, "run_agent", fake_run)
    monkeypatch.setattr(run_module, "codex_other_servers", lambda: ["Playwright"])
    result = run_one("codex", "gpt-5.6-terra", scenario("open_bugs"), 0, 30, source="synthetic")
    overrides = [seen["command"][i + 1] for i, part in enumerate(seen["command"]) if part == "-c"]
    assert f'mcp_servers.backlog.env={{BACKLOG_WORKSPACE_PATH="{seen["cwd"]}"}}' in overrides
    assert "mcp_servers.Playwright.enabled=false" in overrides
    assert "BACKLOG_API_KEY" not in seen["env"]
    assert result["wallClockMs"] == result["processMs"]


def test_codex_other_servers_lists_enabled_servers_except_backlog(monkeypatch):
    import subprocess

    import evals.run as run_module

    listing = json.dumps([{"name": "Playwright", "enabled": True}, {"name": "backlog", "enabled": True},
                          {"name": "old", "enabled": False}, {"name": "exa", "enabled": True}])
    monkeypatch.setattr(run_module.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=listing, stderr=""))
    assert run_module.codex_other_servers() == ["Playwright", "exa"]


def test_run_agent_gives_the_agent_no_stdin(tmp_path):
    import sys
    import time

    from evals.run import run_agent

    script = "import sys\nsys.stdin.read()\nprint('{\"type\":\"result\"}', flush=True)\n"
    started = time.monotonic()
    proc = run_agent([sys.executable, "-c", script], cwd=tmp_path, env=None, timeout_s=20, grace_s=0)
    assert time.monotonic() - started < 10 and proc.timed_out is False and proc.lines == ['{"type":"result"}']
