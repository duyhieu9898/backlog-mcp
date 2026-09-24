import os

from backlog_tool import telemetry
from backlog_tool.claude_transcripts import read_prompt_turns, turn_to_flow
from backlog_tool.telemetry_store import Call

SAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "claude_transcript_sample.jsonl")


def test_only_real_prompts_are_turns():
    turns = read_prompt_turns(SAMPLE)
    assert [t.prompt for t in turns] == ["backlog resolve OOP-12781, bug này tôi fix rồi", "cảm ơn", "OOP-12777 tôi fix rồi"]
    first = turns[0]
    assert first.model == "claude-opus-5-5"
    assert [u["name"] for u in first.tool_uses] == ["Bash", "mcp__backlog__resolve_bug"]
    assert first.final_answer == "Đã resolve OOP-12781."
    assert first.project_dir == "/home/u/proj"


def test_turn_to_flow_matches_telemetry_call_and_keeps_non_mcp():
    turn = read_prompt_turns(SAMPLE)[0]
    matching = Call(
        trace_id="real", ts="2026-09-23T17:20:09.000+07:00", tool="resolve_bug",
        arguments={"issue_key": "OOP-12781", "mode": "apply"}, status="ok", duration_ms=1500, api_calls=2,
        response_bytes=800, est_tokens=200, client="claude-code", session_id="s", surface="mcp", run_id=None,
        scenario=None, issue_key="OOP-12781", project_key="OOP", result={"ok": True},
    )
    flow = turn_to_flow(turn, [matching])
    assert [c.trace_id for c in flow.calls] == ["real"]
    assert flow.non_mcp == [{"name": "Bash", "input": {"command": "git log -1"}}]
    assert flow.prompt == turn.prompt and flow.final_answer == "Đã resolve OOP-12781."
    assert flow.model == "claude-opus-5-5"


def test_follow_up_prompt_without_backlog_word_keeps_its_tool_calls():
    turn = read_prompt_turns(SAMPLE)[2]
    assert [u["name"] for u in turn.tool_uses] == ["mcp__backlog__resolve_bug"]


def test_turn_to_flow_without_telemetry_uses_transcript_call():
    turn = read_prompt_turns(SAMPLE)[0]
    flow = turn_to_flow(turn, [])
    assert [c.tool for c in flow.calls] == ["resolve_bug"]
    assert flow.calls[0].trace_id.startswith("transcript:")
