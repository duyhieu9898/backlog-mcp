"""Read telemetry files into calls and group them into flows (one user request ≈ one flow)."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from . import settings


@dataclass
class Call:
    trace_id: str
    ts: str
    tool: str
    arguments: dict
    status: str
    duration_ms: float
    api_calls: int
    response_bytes: int
    est_tokens: int
    client: str
    session_id: str
    surface: str
    run_id: str | None
    scenario: str | None
    issue_key: str | None
    project_key: str | None
    result: object = None
    text: str | None = None
    mutation: dict | None = None
    errors: list = field(default_factory=list)


@dataclass
class Flow:
    flow_id: str
    calls: list
    prompt: str | None = None
    final_answer: str | None = None
    non_mcp: list = field(default_factory=list)
    schema_reads: int = 0
    denied: list = field(default_factory=list)
    model: str | None = None
    client: str | None = None
    wall_clock_ms: float | None = None
    startup_ms: float | None = None

    @property
    def tools(self):
        return [call.tool for call in self.calls]

    @property
    def started_at(self):
        return self.calls[0].ts if self.calls else None


def _read_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _rotated(path):
    return [f"{path}.{index}" for index in range(5, 0, -1)] + [path]


def load_calls(log_dir=None, since=None, run_id=None):
    log_dir = log_dir or settings.LOG_DIR
    index = [row for path in _rotated(os.path.join(log_dir, "calls.jsonl")) for row in _read_jsonl(path)]
    # Skip rows without traceId
    index = [row for row in index if "traceId" in row]
    if since:
        index = [row for row in index if (row.get("ts") or "") >= since]
    if run_id:
        index = [row for row in index if row.get("runId") == run_id]
    wanted = {row["traceId"] for row in index}

    details = {}
    details_dir = os.path.join(log_dir, "details")
    if os.path.isdir(details_dir):
        for name in sorted(os.listdir(details_dir)):
            if since and name[:10] < since[:10]:
                continue
            for row in _read_jsonl(os.path.join(details_dir, name)):
                if row.get("traceId") in wanted:
                    details[row["traceId"]] = row

    errors = {}
    for path in _rotated(os.path.join(log_dir, "errors.jsonl")):
        for row in _read_jsonl(path):
            if row.get("traceId") in wanted:
                errors.setdefault(row["traceId"], []).append(row)

    calls = []
    for row in sorted(index, key=lambda item: item.get("ts") or ""):
        trace_id = row.get("traceId")
        if not trace_id:
            continue
        detail = details.get(trace_id, {})
        calls.append(Call(
            trace_id=trace_id,
            ts=row.get("ts") or "",
            tool=row.get("tool") or "unknown",
            arguments=detail.get("arguments") or {},
            status=row.get("status") or "unknown",
            duration_ms=row.get("durationMs") or 0,
            api_calls=row.get("apiCalls") or 0,
            response_bytes=row.get("responseBytes") or 0,
            est_tokens=row.get("estTokens") or 0,
            client=(row.get("client") or {}).get("name") or "unknown",
            session_id=row.get("sessionId") or "",
            surface=row.get("surface") or "mcp",
            run_id=row.get("runId"),
            scenario=row.get("scenario"),
            issue_key=row.get("issueKey"),
            project_key=row.get("projectKey"),
            result=detail.get("result"),
            text=detail.get("text"),
            mutation=detail.get("mutation"),
            errors=errors.get(trace_id, []),
        ))
    return calls


def _seconds_between(earlier, later):
    try:
        return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _fits(flow, call, gap_seconds):
    last = flow.calls[-1]
    if last.session_id != call.session_id:
        return False
    if _seconds_between(last.ts, call.ts) > gap_seconds:
        return False
    issues = {c.issue_key for c in flow.calls if c.issue_key}
    if call.issue_key and issues and call.issue_key not in issues:
        return False
    projects = {c.project_key for c in flow.calls if c.project_key}
    if call.project_key and projects and call.project_key not in projects:
        return False
    return True


def group_flows(calls, gap_seconds=180):
    by_run = {}
    heuristic = []
    for call in calls:
        if call.run_id:
            by_run.setdefault(call.run_id, Flow(call.run_id, [], client=call.client)).calls.append(call)
        else:
            heuristic.append(call)

    flows = list(by_run.values())
    open_flows = []
    for call in heuristic:
        target = next((flow for flow in reversed(open_flows) if _fits(flow, call, gap_seconds)), None)
        if target is None:
            target = Flow(f"flow-{call.trace_id[:8]}", [], client=call.client)
            open_flows.append(target)
        target.calls.append(call)
    flows.extend(open_flows)
    flows.sort(key=lambda flow: flow.started_at or "")
    return flows
