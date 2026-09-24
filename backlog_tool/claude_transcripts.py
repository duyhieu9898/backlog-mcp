"""Read Claude Code transcripts (~/.claude/projects/*/*.jsonl) into prompt turns and flows."""

import glob
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime

from .telemetry_store import Call, Flow

MCP_PREFIX = "mcp__backlog__"
MATCH_WINDOW_SECONDS = 5
EVAL_DIR_MARKER = "backlog-eval-"
_WRAPPED = re.compile(
    r"^\s*(<(system-reminder|command-name|command-message|command-args|local-command-stdout|local-command-caveat)\b"
    r"|Base directory for this skill:|\[Request interrupted|Caveat: )"
)


@dataclass
class PromptTurn:
    prompt: str
    ts: str
    model: str | None = None
    tool_uses: list = field(default_factory=list)
    final_answer: str | None = None
    project_dir: str | None = None
    session_file: str | None = None


def _prompt_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return None if _WRAPPED.match(content) else content.strip()
    if isinstance(content, list):
        if any(part.get("type") == "tool_result" for part in content if isinstance(part, dict)):
            return None
        texts = [
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and not _WRAPPED.match(part.get("text", ""))
        ]
        texts = [text for text in texts if text]
        return "\n".join(texts) or None
    return None


def read_prompt_turns(path):
    turns = []
    current = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") or {}
            if entry.get("type") == "user" and not entry.get("isMeta"):
                prompt = _prompt_text(message)
                if prompt:
                    current = PromptTurn(prompt, entry.get("timestamp", ""), project_dir=entry.get("cwd"), session_file=path)
                    turns.append(current)
                    continue
                for part in message.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "tool_result" and current:
                        for use in current.tool_uses:
                            if use.get("id") == part.get("tool_use_id"):
                                use["is_error"] = bool(part.get("is_error"))
            elif entry.get("type") == "assistant" and current:
                current.model = message.get("model") or current.model
                for part in message.get("content") or []:
                    if part.get("type") == "tool_use":
                        current.tool_uses.append({
                            "id": part.get("id"), "name": part.get("name"), "input": part.get("input") or {},
                            "ts": entry.get("timestamp", ""), "is_error": False,
                        })
                        current.final_answer = None
                    elif part.get("type") == "text" and part.get("text", "").strip():
                        current.final_answer = part["text"].strip()
    return turns


def find_transcripts(since=None, root=None):
    root = root or os.path.expanduser("~/.claude/projects")
    paths = [
        p for p in glob.glob(os.path.join(root, "*", "*.jsonl"))
        if EVAL_DIR_MARKER not in os.path.basename(os.path.dirname(p))
    ]
    if since:
        cutoff = datetime.fromisoformat(since[:10]).timestamp()
        paths = [p for p in paths if os.path.getmtime(p) >= cutoff]
    return sorted(paths)


def is_eval_turn(turn):
    """Turns run by the eval harness (evals/run.py works in tempdir/backlog-eval-*)."""
    return bool(turn.project_dir) and turn.project_dir.startswith(os.path.join(tempfile.gettempdir(), EVAL_DIR_MARKER))


def _epoch(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def _call_start(call):
    """Telemetry ts is written when the call finishes; the tool_use happens at its start."""
    finished = _epoch(call.ts)
    return None if finished is None else finished - (call.duration_ms or 0) / 1000


def turn_to_flow(turn, calls):
    flow = Flow(f"prompt-{turn.ts}", [], prompt=turn.prompt, final_answer=turn.final_answer, model=turn.model, client="claude-code")
    used = set()
    for index, use in enumerate(turn.tool_uses):
        name = use["name"] or ""
        if not name.startswith(MCP_PREFIX):
            flow.non_mcp.append({"name": name, "input": use["input"]})
            continue
        tool = name[len(MCP_PREFIX):]
        use_time = _epoch(use["ts"])
        match = next((
            call for call in calls
            if call.trace_id not in used and call.tool == tool and call.arguments == use["input"]
            and use_time is not None and _call_start(call) is not None
            and abs(_call_start(call) - use_time) <= MATCH_WINDOW_SECONDS
        ), None)
        if match is None:
            match = Call(
                trace_id=f"transcript:{index}", ts=use["ts"], tool=tool, arguments=use["input"],
                status="error" if use.get("is_error") else "ok", duration_ms=0, api_calls=0,
                response_bytes=0, est_tokens=0, client="claude-code", session_id="", surface="mcp",
                run_id=None, scenario=None, issue_key=use["input"].get("issue_key"), project_key=None,
            )
        used.add(match.trace_id)
        flow.calls.append(match)
    return flow
