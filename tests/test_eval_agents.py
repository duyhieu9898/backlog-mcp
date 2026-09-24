import os

from evals.agents import agy_command, claude_command, parse_agy, parse_claude

STREAMS = os.path.join(os.path.dirname(__file__), "fixtures", "agent_streams")


def lines(name):
    with open(os.path.join(STREAMS, name), encoding="utf-8") as handle:
        return handle.readlines()


def test_parse_claude():
    trace = parse_claude(lines("claude_sample.jsonl"))
    assert trace.model == "claude-opus-5-5"
    assert trace.mcp_tools == [{"tool": "resolve_bug", "arguments": {"issue_key": "OOP-912762", "mode": "apply"}}]
    assert trace.non_mcp == [{"name": "Grep", "input": {"pattern": "fix"}}]
    assert trace.denied == ["Bash"]
    assert trace.final_answer == "Đã resolve OOP-912762."
    assert trace.wall_clock_ms == 9120 and trace.turns == 3 and trace.raw_ok is True


def test_parse_agy():
    trace = parse_agy(lines("agy_sample.jsonl"))
    assert trace.mcp_tools == [{"tool": "resolve_bug", "arguments": {"issue_key": "OOP-912762", "mode": "apply"}}]
    assert trace.schema_reads == 1
    assert trace.non_mcp == [{"name": "run_command", "input": {"CommandLine": "ls"}}]
    assert trace.final_answer == "Đã resolve OOP-912762."
    assert trace.wall_clock_ms == 12500 and trace.raw_ok is True


def test_parse_truncated_stream_is_not_ok():
    trace = parse_agy(lines("agy_sample.jsonl")[:-1])
    assert trace.raw_ok is False and trace.final_answer is None


def test_commands_restrict_tools_and_use_stream_json():
    claude = claude_command("p", "opus", "/tmp/x/mcp.json")
    assert claude[:2] == ["claude", "-p"] and "--disallowedTools" in claude and "stream-json" in claude
    assert "--strict-mcp-config" in claude
    assert claude[claude.index("--mcp-config") + 1] == "/tmp/x/mcp.json"
    for tool in ("Bash", "Edit", "Write", "Task", "Agent", "WebFetch", "WebSearch"):
        assert tool in claude
    agy = agy_command("p", "gemini-3.8-flash-medium", 300)
    assert "--sandbox" not in agy and "--dangerously-skip-permissions" in agy and "--model" in agy


def test_parse_agy_counts_steps():
    assert parse_agy(lines("agy_sample.jsonl")).steps == 3


def test_parse_agy_result_without_steps_is_not_ok():
    stream = [lines("agy_sample.jsonl")[0], lines("agy_sample.jsonl")[1],
              '{"event":"result","result":{"status":"SUCCESS","response":"","duration_seconds":0,"num_turns":0}}']
    trace = parse_agy(stream)
    assert trace.steps == 0 and trace.raw_ok is False


def test_parse_agy_failed_status_is_not_ok():
    stream = [*lines("agy_sample.jsonl")[:-1],
              '{"event":"result","result":{"status":"ERROR","response":"x","duration_seconds":1,"num_turns":1}}']
    assert parse_agy(stream).raw_ok is False
