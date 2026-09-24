"""Build readable reports from telemetry flows (tier 1 aggregates + tier 2 rules + tier 3 grades)."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .claude_transcripts import find_transcripts, is_eval_turn, read_prompt_turns, turn_to_flow
from .telemetry_grader import expect_for, grade, load_scenarios, match_prompt, render_scenario
from .telemetry_rules import apply_rules
from .telemetry_store import group_flows, load_calls

_RELATIVE = re.compile(r"^(\d+)([dh])$")


def parse_since(value):
    if not value:
        return None
    match = _RELATIVE.match(value)
    if not match:
        return value
    amount, unit = int(match.group(1)), match.group(2)
    delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
    return (datetime.now().astimezone() - delta).isoformat(timespec="seconds")


def _grade_for(flow, scenarios):
    scenario_id = next((c.scenario for c in flow.calls if c.scenario), None)
    if scenario_id:
        scenario = next((s for s in scenarios if s["id"] == scenario_id), None)
        if scenario:
            return scenario_id, grade(render_scenario(scenario)["expect"], flow, flow.final_answer)
    if flow.prompt:
        matched = match_prompt(flow.prompt, scenarios)
        if matched:
            scenario, keys = matched
            return scenario["id"], grade(expect_for(scenario, keys), flow, flow.final_answer)
    return None, None


def flow_summary(flow, scenarios):
    scenario_id, result = _grade_for(flow, scenarios)
    summary = {
        "flowId": flow.flow_id,
        "startedAt": flow.started_at,
        "prompt": flow.prompt,
        "model": flow.model,
        "client": flow.client,
        "tools": flow.tools,
        "nonMcp": [item["name"] for item in flow.non_mcp],
        "estTokens": sum(c.est_tokens for c in flow.calls),
        "durationMs": round(sum(c.duration_ms for c in flow.calls), 1),
        "findings": apply_rules(flow, flow.final_answer),
    }
    if result is not None:
        summary["scenario"] = scenario_id
        summary["grade"] = result
    return summary


def build_report(flows, scenarios):
    summaries = [flow_summary(flow, scenarios) for flow in flows]
    calls = [call for flow in flows for call in flow.calls]

    by_tool = defaultdict(lambda: {"calls": 0, "estTokens": 0, "durationMs": 0.0, "errors": 0})
    for call in calls:
        row = by_tool[call.tool]
        row["calls"] += 1
        row["estTokens"] += call.est_tokens
        row["durationMs"] += call.duration_ms
        row["errors"] += int(call.status != "ok")
    top_tools = sorted(
        ({"tool": tool, **row, "durationMs": round(row["durationMs"], 1)} for tool, row in by_tool.items()),
        key=lambda row: -row["estTokens"],
    )

    errors = Counter()
    for call in calls:
        for error in call.errors:
            detail = ",".join(error.get("unknown") or []) if error.get("kind") == "arg_error" else error.get("message", "")
            errors[(error.get("kind"), call.tool, detail)] += 1
    recurring = [
        {"kind": kind, "tool": tool, "detail": detail, "count": count}
        for (kind, tool, detail), count in errors.most_common()
    ]

    by_client = defaultdict(lambda: {"flows": 0, "calls": 0, "estTokens": 0})
    for flow in flows:
        key = flow.model or flow.client or "unknown"
        by_client[key]["flows"] += 1
        by_client[key]["calls"] += len(flow.calls)
        by_client[key]["estTokens"] += sum(c.est_tokens for c in flow.calls)

    pass_rate = defaultdict(lambda: {"pass": 0, "runs": 0})
    for summary in summaries:
        if "grade" in summary:
            pass_rate[summary["scenario"]]["runs"] += 1
            pass_rate[summary["scenario"]]["pass"] += int(summary["grade"]["pass"])

    return {
        "flows": summaries,
        "totals": {"flows": len(flows), "calls": len(calls), "estTokens": sum(c.est_tokens for c in calls)},
        "topTools": top_tools,
        "recurringErrors": recurring,
        "byClient": dict(by_client),
        "passRate": dict(pass_rate),
    }


def report_from_logs(since=None, run_id=None, log_dir=None):
    flows = group_flows(load_calls(log_dir=log_dir, since=parse_since(since), run_id=run_id))
    return build_report(flows, load_scenarios())


def _instant(value):
    """Aware datetime for an ISO timestamp (transcripts use UTC `Z`, `since` is local); naive = local time."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def report_from_claude(since=None, root=None, log_dir=None):
    since_iso = parse_since(since)
    since_at = _instant(since_iso) if since_iso else None
    calls = load_calls(log_dir=log_dir, since=since_iso)
    flows = []
    for path in find_transcripts(since_iso, root):
        for turn in read_prompt_turns(path):
            if is_eval_turn(turn):
                continue
            if since_at:
                turn_at = _instant(turn.ts)
                if turn_at is None or turn_at < since_at:
                    continue
            uses_backlog = any((u["name"] or "").startswith("mcp__backlog__") for u in turn.tool_uses)
            if "backlog" not in turn.prompt.lower() and not uses_backlog:
                continue
            flows.append(turn_to_flow(turn, calls))
    return build_report(flows, load_scenarios())


def to_markdown(report):
    lines = [f"Flows: {report['totals']['flows']} · calls: {report['totals']['calls']} · estTokens: {report['totals']['estTokens']}", ""]
    if report["passRate"]:
        lines += ["| Scenario | Pass/Runs |", "|---|---|"]
        lines += [f"| {k} | {v['pass']}/{v['runs']} |" for k, v in sorted(report["passRate"].items())]
        lines.append("")
    lines += ["| Tool | Calls | estTokens | ms | Errors |", "|---|---|---|---|---|"]
    lines += [f"| {r['tool']} | {r['calls']} | {r['estTokens']} | {r['durationMs']} | {r['errors']} |" for r in report["topTools"]]
    if report["recurringErrors"]:
        lines += ["", "| Error | Tool | Detail | Count |", "|---|---|---|---|"]
        lines += [f"| {e['kind']} | {e['tool']} | {e['detail'][:60]} | {e['count']} |" for e in report["recurringErrors"][:15]]
    lines += ["", "| Flow | Tools | Findings | Grade |", "|---|---|---|---|"]
    for flow in report["flows"]:
        grade_text = "" if "grade" not in flow else ("PASS" if flow["grade"]["pass"] else "FAIL: " + "; ".join(flow["grade"]["reasons"])[:80])
        findings = ",".join(sorted({f["code"] for f in flow["findings"]}))
        lines.append(f"| {flow['flowId'][:24]} | {' → '.join(flow['tools'])} | {findings} | {grade_text} |")
    return "\n".join(lines)
