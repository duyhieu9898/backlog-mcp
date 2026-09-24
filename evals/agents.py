"""Commands and stream-json parsers for the agents we evaluate (Claude Code, Antigravity CLI)."""

import json
from dataclasses import dataclass, field

CLAUDE_MCP_PREFIX = "mcp__backlog__"
# In the user's auto permission mode --allowedTools does not block other tools, so MCP servers are
# isolated with --strict-mcp-config (only our backlog server) and built-in tools are denied explicitly.
CLAUDE_DISALLOWED = ["Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent"]
AGY_SCHEMA_DIR = "/.gemini/antigravity-cli/mcp/backlog/"


@dataclass
class AgentTrace:
    model: str | None = None
    final_answer: str | None = None
    mcp_tools: list = field(default_factory=list)
    non_mcp: list = field(default_factory=list)
    schema_reads: int = 0
    denied: list = field(default_factory=list)
    wall_clock_ms: float | None = None
    turns: int | None = None
    raw_ok: bool = False


def _events(lines):
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def claude_command(prompt, model, mcp_config_path):
    return [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--mcp-config", str(mcp_config_path),
        "--disallowedTools", *CLAUDE_DISALLOWED,
    ]


def agy_command(prompt, model, timeout_s):
    return [
        "agy", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions", "--sandbox",
        "--print-timeout", f"{int(timeout_s)}s",
    ]


def parse_claude(lines):
    trace = AgentTrace()
    for event in _events(lines):
        kind = event.get("type")
        if kind == "assistant":
            message = event.get("message") or {}
            trace.model = message.get("model") or trace.model
            for part in message.get("content") or []:
                if part.get("type") != "tool_use":
                    continue
                name = part.get("name") or ""
                if name.startswith(CLAUDE_MCP_PREFIX):
                    trace.mcp_tools.append({"tool": name[len(CLAUDE_MCP_PREFIX):], "arguments": part.get("input") or {}})
                else:
                    trace.non_mcp.append({"name": name, "input": part.get("input") or {}})
        elif kind == "result":
            trace.final_answer = event.get("result")
            trace.wall_clock_ms = event.get("duration_ms")
            trace.turns = event.get("num_turns")
            trace.denied = [d.get("tool_name") for d in event.get("permission_denials") or []]
            trace.raw_ok = not event.get("is_error")
    return trace


def parse_agy(lines):
    trace = AgentTrace()
    for event in _events(lines):
        if event.get("event") == "step_update":
            step = event["step_update"]
            if step.get("state") != "DONE" or step.get("step_type") != "tool":
                continue
            info = step.get("tool_info") or {}
            params = info.get("parameters") or {}
            name = step.get("tool_name")
            if name == "call_mcp_tool" and params.get("ServerName") == "backlog":
                trace.mcp_tools.append({"tool": params.get("ToolName"), "arguments": params.get("Arguments") or {}})
            elif name == "view_file" and AGY_SCHEMA_DIR in (params.get("AbsolutePath") or ""):
                trace.schema_reads += 1
            else:
                trace.non_mcp.append({"name": name, "input": params})
        elif event.get("event") == "result":
            result = event["result"]
            trace.final_answer = (result.get("response") or "").strip() or None
            seconds = result.get("duration_seconds")
            trace.wall_clock_ms = round(seconds * 1000) if seconds is not None else None
            trace.turns = result.get("num_turns")
            trace.raw_ok = result.get("status") == "SUCCESS"
    return trace


AGENTS = {
    "claude": (claude_command, parse_claude),
    "agy": (agy_command, parse_agy),
}
