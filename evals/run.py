"""Run eval scenarios through a real agent (claude/agy) against the fake Backlog and grade the logs."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from backlog_tool import settings
from backlog_tool.telemetry_grader import grade, load_scenarios, render_scenario
from backlog_tool.telemetry_store import Flow, group_flows, load_calls
from evals.agents import AGENTS
from evals.fake_backlog import FakeBacklog

RESULTS_ROOT = Path(__file__).resolve().parent / "results"
WORKSPACE_MARKERS = (".backlog-project.json", ".backlog-eval.json")
ISOLATION_REASON = "isolation: server did not run on the fake backend"


@dataclass
class AgentProcess:
    lines: list
    stderr_tail: str
    timed_out: bool


def _is_result_event(line):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(event, dict) and (event.get("type") == "result" or event.get("event") == "result")


def run_agent(command, cwd, env, timeout_s, grace_s=30):
    """Stream the agent's stdout and stop it at the result event (agy keeps running until --print-timeout)."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr, text=True)
        timed_out = threading.Event()

        def kill():
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(timeout_s + grace_s, kill)
        watchdog.start()
        lines = []
        try:
            for line in proc.stdout:
                lines.append(line.rstrip("\n"))
                if _is_result_event(line):
                    break
        finally:
            watchdog.cancel()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        stderr.seek(0)
        return AgentProcess(lines=lines, stderr_tail=stderr.read()[-2000:], timed_out=timed_out.is_set())


ENV_ERROR_MARKERS = (
    ("service_unavailable", ("UNAVAILABLE", "code 503", "RESOURCE_EXHAUSTED", "code 429")),
    ("sandbox", ("sandbox server",)),
)


def classify_env_error(proc, trace):
    """Name the environment failure behind a run, so SUMMARY.md does not blame the model for it."""
    text = proc.stderr_tail + "\n" + "\n".join(line for line in proc.lines if not line.lstrip().startswith("{"))
    for label, markers in ENV_ERROR_MARKERS:
        if any(marker in text for marker in markers):
            return label
    if proc.timed_out:
        return "timeout"
    if not trace.raw_ok:
        return "agent_failed"
    return None


def _agy_enabled_servers():
    listing = subprocess.run(["agy", "mcp", "list"], capture_output=True, text=True, timeout=60, check=True).stdout
    servers = []
    for row in listing.splitlines()[1:]:
        parts = row.split()
        if len(parts) >= 3 and parts[2] == "enabled" and parts[0] != "backlog":
            servers.append(parts[0])
    return servers


def codex_other_servers():
    """Global Codex MCP servers to switch off per run (with -c, no config change)."""
    listing = subprocess.run(["codex", "mcp", "list", "--json"], capture_output=True, text=True, timeout=60, check=True).stdout
    return [s["name"] for s in json.loads(listing) if s.get("enabled") and s.get("name") != "backlog"]


@contextmanager
def agy_mcp_isolated():
    """agy has no --strict-mcp-config: disable other global MCP servers for the batch, then re-enable them."""
    disabled = []
    try:
        for name in _agy_enabled_servers():
            subprocess.run(["agy", "mcp", "disable", name], capture_output=True, text=True, timeout=60, check=True)
            disabled.append(name)
        if disabled:
            print(f"agy: tạm tắt MCP server {', '.join(disabled)}", flush=True)
        yield disabled
    finally:
        for name in disabled:
            subprocess.run(["agy", "mcp", "enable", name], capture_output=True, text=True, timeout=60)
        if disabled:
            print(f"agy: đã bật lại {', '.join(disabled)}", flush=True)


def agent_env(workspace):
    """Agent subprocess env without any real Backlog credentials (bootstrap loads .env into os.environ)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("BACKLOG_")}
    env["BACKLOG_WORKSPACE_PATH"] = str(workspace)
    return env


def write_mcp_config(folder):
    """Per-run MCP config for --strict-mcp-config: only this repo's backlog server."""
    path = Path(folder) / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"backlog": {
        "command": "uv", "args": ["--project", settings.MCP_ROOT, "run", "backlog-mcp-server"],
    }}}))
    return path


def ran_on_fake_backend(log_dir, run_id):
    path = Path(log_dir) / "sessions.jsonl"
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("backend") == "fake" and row.get("runId") == run_id:
            return True
    return False


def snapshot_markers(workspace):
    return {name: (Path(workspace) / name).read_bytes() if (Path(workspace) / name).exists() else None
            for name in WORKSPACE_MARKERS}


def restore_markers(workspace, originals):
    for name, content in originals.items():
        path = Path(workspace) / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(content)


def config_fingerprint(agent):
    """Which agent build, server code and tool descriptions produced a run."""
    import hashlib

    import anyio

    from backlog_mcp import server
    from backlog_tool.telemetry import server_version

    try:
        agent_version = subprocess.run([agent, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        agent_version = None
    tools = anyio.run(server.mcp.list_tools)
    described = json.dumps([[t.name, t.description, t.inputSchema] for t in tools], sort_keys=True, ensure_ascii=False)
    return {
        "agentVersion": agent_version,
        "gitSha": server_version()["gitSha"],
        "toolsHash": hashlib.sha256(described.encode("utf-8")).hexdigest()[:12],
        "toolCount": len(tools),
    }


def prepare_workspace(root, scenario, run_id, base_url, log_dir):
    workspace = Path(root)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".backlog-project.json").write_text(json.dumps({"project_key": "OOP"}))
    (workspace / ".backlog-eval.json").write_text(json.dumps({
        "baseUrl": base_url, "logDir": str(log_dir), "runId": run_id, "scenario": scenario["id"],
    }))
    return workspace


def grade_run(scenario, trace, log_dir, run_id):
    flows = group_flows(load_calls(log_dir=str(log_dir), run_id=run_id)) if Path(log_dir).exists() else []
    flow = flows[0] if flows else Flow(run_id, [])
    result = grade(scenario["expect"], flow, final_answer=trace.final_answer, require_final_answer=True)
    result.update({
        "schemaReads": trace.schema_reads,
        "deniedTools": trace.denied,
        "nonMcpCalls": [item["name"] for item in trace.non_mcp],
        "wallClockMs": trace.wall_clock_ms,
        "turns": trace.turns,
        "agentOk": trace.raw_ok,
        "mcpCallsSeenByAgent": len(trace.mcp_tools),
        "finalAnswer": (trace.final_answer or "")[:500],
    })
    if not ran_on_fake_backend(log_dir, run_id):
        result["isolationFailed"] = True
        result["pass"] = False
        result["reasons"] = [*result["reasons"], ISOLATION_REASON]
    return result


def run_one(agent, model, scenario, index, timeout_s, workspace=None, source="cassette"):
    build_command, parse = AGENTS[agent]
    run_id = f"{agent}-{scenario['id']}-{index}-{uuid.uuid4().hex[:6]}"
    with tempfile.TemporaryDirectory(prefix="backlog-eval-") as tmp:
        root = Path(workspace) if workspace else Path(tmp) / "ws"
        log_dir = Path(tmp) / "logs"
        originals = snapshot_markers(root) if workspace else {}
        try:
            with FakeBacklog(state=scenario["fakeState"], source=source) as fake:
                ws = prepare_workspace(root, scenario, run_id, fake.base_url, log_dir)
                if agent == "claude":
                    command = build_command(scenario["prompt"], model, write_mcp_config(tmp))
                elif agent == "codex":
                    command = build_command(scenario["prompt"], model, ws, codex_other_servers())
                else:
                    command = build_command(scenario["prompt"], model, timeout_s)
                started = time.monotonic()
                proc = run_agent(command, cwd=ws, env=agent_env(ws), timeout_s=timeout_s)
                elapsed_ms = round((time.monotonic() - started) * 1000)
                trace = parse(proc.lines)
                if agent == "codex":
                    trace.wall_clock_ms = elapsed_ms  # codex --json reports no duration
                result = grade_run(scenario, trace, log_dir, run_id)
                result.update({
                    "runId": run_id, "agent": agent, "model": model, "scenario": scenario["id"], "backendSource": fake.source,
                    "processMs": elapsed_ms, "unhandledEndpoints": fake.unhandled,
                    "patches": [p["key"] for p in fake.patches],
                    "envError": classify_env_error(proc, trace),
                    "stderrTail": proc.stderr_tail if not trace.raw_ok else "",
                })
        finally:
            if workspace:
                restore_markers(root, originals)
    return result


def _median(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(statistics.median(values)) if values else "-"


def write_summary(folder):
    folder = Path(folder)
    lines = [f"# Eval summary — {folder.name}", ""]
    for path in sorted(folder.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        by_scenario = defaultdict(list)
        reasons = defaultdict(int)
        env_errors = defaultdict(int)
        for row in rows:
            by_scenario[row["scenario"]].append(row)
            if row.get("envError") and not row.get("pass"):
                env_errors[row["envError"]] += 1
                continue
            for reason in row.get("reasons") or []:
                reasons[reason.split(":")[0]] += 1
        lines += [f"## {path.stem}", "", "| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |",
                  "|---|---|---|---|---|---|"]
        for scenario, group in sorted(by_scenario.items()):
            ok = sum(bool(row.get("pass")) for row in group)
            env = sum(bool(row.get("envError")) and not row.get("pass") for row in group)
            arg = sum(bool(row.get("argErrors")) for row in group)
            tokens = _median(row.get("estTokens") for row in group)
            wall = _median(row.get("wallClockMs") for row in group)
            lines.append(f"| {scenario} | {ok}/{len(group)} | {env} | {arg} | {tokens} | {wall} |")
        if reasons:
            lines += ["", "Lý do fail phổ biến: " + ", ".join(f"{k} ×{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))]
        if env_errors:
            lines += ["", "Lỗi môi trường: " + ", ".join(f"{k} ×{v}" for k, v in sorted(env_errors.items(), key=lambda kv: -kv[1]))]
        lines.append("")
    (folder / "SUMMARY.md").write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Backlog MCP eval scenarios through a real agent.")
    parser.add_argument("--agent", required=True, choices=sorted(AGENTS))
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--label", default="adhoc")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workspace", help="Run inside this directory instead of a temp workspace")
    parser.add_argument("--allow-synthetic", action="store_true", help="Use synthetic issues when no local cassette exists")
    args = parser.parse_args(argv)

    scenarios = [render_scenario(s) for s in load_scenarios() if args.scenario in ("all", s["id"])]
    folder = RESULTS_ROOT / f"{date.today().isoformat()}-{args.label}"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{args.agent}-{args.model}.jsonl"
    fingerprint = config_fingerprint(args.agent)
    with agy_mcp_isolated() if args.agent == "agy" else nullcontext():
        return _run_batch(args, scenarios, folder, out, fingerprint)


def _run_batch(args, scenarios, folder, out, fingerprint):
    for scenario in scenarios:
        for index in range(args.runs):
            result = run_one(args.agent, args.model, scenario, index, args.timeout, args.workspace,
                             source="auto" if args.allow_synthetic else "cassette")
            result["configFingerprint"] = fingerprint
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            status = "PASS" if result["pass"] else "FAIL " + "; ".join(result["reasons"])[:120]
            if result.get("envError") and not result["pass"]:
                status = f"ENV({result['envError']}) " + status
            print(f"[{scenario['id']} #{index + 1}] {status}", flush=True)
            if result.get("isolationFailed"):
                write_summary(folder)
                print("ISOLATION FAILED: the MCP server did not run on the fake backend "
                      f"(no fake session row for {result.get('runId')}). Batch stopped; check the agent's MCP config.",
                      flush=True)
                return 2
    write_summary(folder)
    print(f"Results: {out}\nSummary: {folder / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
