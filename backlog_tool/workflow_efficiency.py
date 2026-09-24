"""Rule-based analysis of vendor-neutral MCP telemetry.

The analyzer intentionally evaluates observable behavior only. It does not try
to infer model reasoning or claim a user intent that was never recorded.
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from . import settings

TASK_GAP_SECONDS = 180
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")

MUTATION_TOOLS = {"create_issue", "update_issue", "resolve_bug", "create_ut_bug"}


def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _telemetry_paths():
    path = os.path.join(settings.LOG_DIR, "telemetry.jsonl")
    candidates = [path] + [f"{path}.{index}" for index in range(1, 6)]
    return [item for item in candidates if os.path.exists(item)]


def read_telemetry():
    records = []
    for path in reversed(_telemetry_paths()):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    records.sort(key=lambda item: item.get("ts") or "")
    return records


def _issue_from_arguments(arguments: dict[str, Any]):
    for key in ("issue_key", "issue_ref", "issue_id", "parent_key"):
        value = arguments.get(key)
        if isinstance(value, str) and ISSUE_KEY_RE.match(value):
            return value
    return None


def _project_from_arguments(arguments: dict[str, Any], issue_key: str | None):
    explicit = arguments.get("project_key")
    if explicit:
        return str(explicit)
    if issue_key:
        return issue_key.rsplit("-", 1)[0]
    return None


def _call_subject(call):
    if call.get("issueKey"):
        return ("issue", call["issueKey"])
    if call.get("project"):
        return ("project", call["project"])
    return None


def build_calls(records=None):
    records = records if records is not None else read_telemetry()
    by_trace = {}

    for record in records:
        trace_id = record.get("traceId")
        if not trace_id:
            continue
        call = by_trace.setdefault(
            trace_id,
            {
                "traceId": trace_id,
                "tool": record.get("tool"),
                "client": (record.get("client") or {}).get("name") or "unknown",
                "clientVersion": (record.get("client") or {}).get("version"),
                "startedAt": None,
                "endedAt": None,
                "arguments": {},
                "status": None,
                "durationMs": 0,
                "totalResponseBytes": 0,
                "estimatedTokens": 0,
                "apiCalls": 0,
                "apiDurationMs": 0,
            },
        )

        event = record.get("event")
        if event == "tool_start":
            call["tool"] = record.get("tool") or call["tool"]
            call["startedAt"] = record.get("ts")
            call["arguments"] = record.get("arguments") or {}
            call["client"] = (record.get("client") or {}).get("name") or call["client"]
            call["clientVersion"] = (record.get("client") or {}).get("version")
        elif event == "api_call":
            call["apiCalls"] += 1
            call["apiDurationMs"] += record.get("durationMs") or 0
        elif event == "tool_end":
            call["endedAt"] = record.get("ts")
            call["status"] = record.get("status")
            call["durationMs"] = record.get("durationMs") or 0
            call["totalResponseBytes"] = record.get("totalResponseBytes") or 0
            call["estimatedTokens"] = record.get("estimatedTokens") or round(
                call["totalResponseBytes"] / 4
            )

    calls = []
    for call in by_trace.values():
        if not call.get("startedAt"):
            continue
        issue_key = _issue_from_arguments(call["arguments"])
        call["issueKey"] = issue_key
        call["project"] = _project_from_arguments(call["arguments"], issue_key)
        calls.append(call)

    calls.sort(key=lambda item: item.get("startedAt") or "")
    return calls


def _task_matches_call(task, call):
    if not task:
        return False
    first = task[0]
    if (first.get("client") or "unknown") != (call.get("client") or "unknown"):
        return False

    call_project = call.get("project")
    task_projects = {item.get("project") for item in task if item.get("project")}
    if call_project and task_projects and call_project not in task_projects:
        return False

    call_issue = call.get("issueKey")
    task_issues = {item.get("issueKey") for item in task if item.get("issueKey")}
    if call_issue and task_issues and call_issue not in task_issues:
        return False

    return True


def group_candidate_tasks(calls):
    tasks = []

    for call in calls:
        started = _parse_ts(call.get("startedAt"))
        if started is None:
            tasks.append([call])
            continue

        matched_index = None
        for index in range(len(tasks) - 1, -1, -1):
            task = tasks[index]
            previous = _parse_ts(task[-1].get("startedAt"))
            if previous is None:
                continue
            gap = (started - previous).total_seconds()
            if gap > TASK_GAP_SECONDS:
                break
            if _task_matches_call(task, call):
                matched_index = index
                break

        if matched_index is None:
            tasks.append([call])
        else:
            tasks[matched_index].append(call)

    return tasks


def _canonical_arguments(arguments):
    return json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _finding(code, reason, *, severity="info", calls=None):
    return {
        "code": code,
        "severity": severity,
        "reason": reason,
        "traceIds": [call["traceId"] for call in (calls or [])],
    }


def analyze_task(calls, index):
    tools = [call.get("tool") for call in calls]
    first = calls[0]
    findings = []

    seen = {}
    for call in calls:
        fingerprint = (call.get("tool"), _canonical_arguments(call.get("arguments")))
        if fingerprint in seen:
            findings.append(
                _finding(
                    "duplicate_same_call",
                    f"{call.get('tool')} was called again with the same arguments in the same candidate task.",
                    severity="warning",
                    calls=[seen[fingerprint], call],
                )
            )
        else:
            seen[fingerprint] = call

    for i, call in enumerate(calls):
        tool = call.get("tool")
        later_tools = tools[i + 1 :]

        if tool == "get_issue" and "get_bug_context" in later_tools:
            findings.append(
                _finding(
                    "generic_lookup_before_bug_context",
                    "get_issue preceded get_bug_context for the same issue; get_bug_context is the personal bug-investigation entry point.",
                    severity="warning",
                    calls=[call, calls[i + 1 + later_tools.index("get_bug_context")]],
                )
            )

        if tool in {"get_bug_rules", "get_bug_fields"} and "resolve_bug" in later_tools:
            findings.append(
                _finding(
                    "diagnostic_prestep_before_resolve",
                    f"{tool} was called before resolve_bug; resolve_bug already loads workflow rules/mappings internally unless clarification is needed.",
                    severity="candidate",
                    calls=[call, calls[i + 1 + later_tools.index("resolve_bug")]],
                )
            )

        if tool == "get_issues" and "get_my_open_bugs" in later_tools:
            findings.append(
                _finding(
                    "generic_search_before_personal_bugs",
                    "get_issues preceded get_my_open_bugs; the personal bug tool should normally be the direct path.",
                    severity="candidate",
                    calls=[call, calls[i + 1 + later_tools.index("get_my_open_bugs")]],
                )
            )

    for mutation in MUTATION_TOOLS:
        mutation_calls = [call for call in calls if call.get("tool") == mutation]
        applies = [call for call in mutation_calls if (call.get("arguments") or {}).get("mode") == "apply"]
        previews = [
            call
            for call in mutation_calls
            if (call.get("arguments") or {}).get("mode", "preview") != "apply"
        ]
        if applies and not previews:
            findings.append(
                _finding(
                    "apply_without_preview",
                    f"{mutation} apply occurred without a matching preview in this candidate task.",
                    severity="warning",
                    calls=applies,
                )
            )

    if (
        "get_my_work_overview" in tools
        and "get_my_open_bugs" in tools
        and "get_my_project_status" not in tools
    ):
        findings.append(
            _finding(
                "split_personal_status_path",
                "Stories/Tasks and open Bugs were fetched separately. If the user asked for combined Backlog status, get_my_project_status is the one-call path.",
                severity="candidate",
                calls=[
                    next(call for call in calls if call.get("tool") == "get_my_work_overview"),
                    next(call for call in calls if call.get("tool") == "get_my_open_bugs"),
                ],
            )
        )

    total_bytes = sum(call.get("totalResponseBytes") or 0 for call in calls)
    api_calls = sum(call.get("apiCalls") or 0 for call in calls)
    api_duration = sum(call.get("apiDurationMs") or 0 for call in calls)
    duration = sum(call.get("durationMs") or 0 for call in calls)

    return {
        "taskId": f"candidate-{index + 1}",
        "client": first.get("client") or "unknown",
        "project": first.get("project"),
        "issueKey": first.get("issueKey"),
        "startedAt": first.get("startedAt"),
        "endedAt": calls[-1].get("endedAt") or calls[-1].get("startedAt"),
        "mcpCalls": len(calls),
        "apiCalls": api_calls,
        "durationMs": round(duration, 1),
        "apiDurationMs": round(api_duration, 1),
        "totalResponseBytes": total_bytes,
        "estimatedTokens": round(total_bytes / 4),
        "tools": tools,
        "statuses": [call.get("status") for call in calls],
        "findings": findings,
    }


def summarize_workflow_efficiency(records=None):
    calls = build_calls(records)
    grouped = group_candidate_tasks(calls)
    tasks = [analyze_task(task, index) for index, task in enumerate(grouped)]

    finding_counts = Counter(
        finding["code"]
        for task in tasks
        for finding in task["findings"]
    )
    by_client = defaultdict(
        lambda: {
            "client": None,
            "tasks": 0,
            "mcpCalls": 0,
            "apiCalls": 0,
            "totalResponseBytes": 0,
            "estimatedTokens": 0,
            "findings": 0,
        }
    )
    for task in tasks:
        bucket = by_client[task["client"]]
        bucket["client"] = task["client"]
        bucket["tasks"] += 1
        bucket["mcpCalls"] += task["mcpCalls"]
        bucket["apiCalls"] += task["apiCalls"]
        bucket["totalResponseBytes"] += task["totalResponseBytes"]
        bucket["estimatedTokens"] += task["estimatedTokens"]
        bucket["findings"] += len(task["findings"])

    client_rows = []
    for bucket in by_client.values():
        tasks_count = bucket["tasks"]
        bucket["avgMcpCallsPerTask"] = round(bucket["mcpCalls"] / tasks_count, 2) if tasks_count else 0
        bucket["avgApiCallsPerTask"] = round(bucket["apiCalls"] / tasks_count, 2) if tasks_count else 0
        bucket["avgResponseBytesPerTask"] = round(bucket["totalResponseBytes"] / tasks_count) if tasks_count else 0
        client_rows.append(bucket)
    client_rows.sort(key=lambda item: item["client"])

    return {
        "schemaVersion": 1,
        "method": {
            "taskGrouping": "heuristic",
            "gapSeconds": TASK_GAP_SECONDS,
            "note": "Candidate tasks are grouped only by observable client + issue/project + time proximity. Findings marked candidate may depend on user intent.",
        },
        "overview": {
            "candidateTasks": len(tasks),
            "mcpCalls": len(calls),
            "apiCalls": sum(task["apiCalls"] for task in tasks),
            "totalResponseBytes": sum(task["totalResponseBytes"] for task in tasks),
            "estimatedTokens": sum(task["estimatedTokens"] for task in tasks),
            "findings": sum(len(task["findings"]) for task in tasks),
        },
        "findingCounts": dict(sorted(finding_counts.items())),
        "clients": client_rows,
        "tasks": tasks,
    }
