import json
import os

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


def test_final_answer_none_when_tool_use_is_last_content(tmp_path):
    """Verify that final_answer is None when tool_use is the last assistant content."""
    transcript_file = tmp_path / "test_transcript.jsonl"
    transcript_data = [
        {"type": "user", "timestamp": "2026-09-23T10:00:00.000Z", "cwd": "/home/u/proj", "message": {"role": "user", "content": "Check bug context"}},
        {"type": "assistant", "timestamp": "2026-09-23T10:00:01.000Z", "message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "Checking."}, {"type": "tool_use", "id": "t1", "name": "mcp__backlog__get_bug_context", "input": {"issue_key": "BUG-123"}}]}},
        {"type": "user", "timestamp": "2026-09-23T10:00:02.000Z", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]}}
    ]
    with open(transcript_file, "w") as f:
        for obj in transcript_data:
            f.write(json.dumps(obj) + "\n")

    turns = read_prompt_turns(str(transcript_file))
    assert len(turns) == 1
    turn = turns[0]
    assert turn.prompt == "Check bug context"
    assert turn.model == "claude-opus-5-5"
    assert [u["name"] for u in turn.tool_uses] == ["mcp__backlog__get_bug_context"]
    assert turn.final_answer is None  # No text after tool_use, so final_answer should be None
