"""Tier-2 rules: observable inefficiencies that apply to every flow, with or without a scenario."""

import json

from .telemetry import LARGE_RESPONSE_BYTES

# (generic tool, specialized tool) pairs where the specialized tool is the intended path.
SPECIALIZED = [("get_issue", "get_bug_context"), ("get_issues", "get_my_open_bugs")]


def _finding(code, reason, calls, severity="warning"):
    return {"code": code, "severity": severity, "reason": reason, "traceIds": [c.trace_id for c in calls]}


def _same_subject(a, b):
    return a.issue_key == b.issue_key or not (a.issue_key and b.issue_key)


def apply_rules(flow, final_answer=None):
    calls = flow.calls
    findings = []

    seen = {}
    for call in calls:
        key = (call.tool, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False))
        if key in seen:
            findings.append(_finding("duplicate_call", f"{call.tool} repeated with identical arguments.", [seen[key], call]))
        else:
            seen[key] = call

    for generic, specialized in SPECIALIZED:
        for i, call in enumerate(calls):
            if call.tool != generic:
                continue
            before = [c for c in calls[:i] if c.tool == specialized and _same_subject(c, call)]
            after = [c for c in calls[i + 1:] if c.tool == specialized and _same_subject(c, call)]
            if before:
                findings.append(_finding(
                    "generic_after_specialized",
                    f"{generic} followed {specialized}; the specialized response may be missing data or the routing is unclear.",
                    [before[-1], call], severity="candidate",
                ))
            if after:
                findings.append(_finding(
                    "generic_before_specialized",
                    f"{generic} preceded {specialized}; {specialized} is the direct path.",
                    [call, after[0]],
                ))

    for i, call in enumerate(calls):
        if any(error.get("kind") == "arg_error" for error in call.errors):
            findings.append(_finding("arg_error", f"{call.tool} was called with invalid arguments.", [call]))
        if call.status != "ok" and i + 1 < len(calls) and calls[i + 1].tool == call.tool:
            findings.append(_finding("retry_after_error", f"{call.tool} retried after status {call.status}.", [call, calls[i + 1]], severity="info"))
        if call.response_bytes > LARGE_RESPONSE_BYTES:
            findings.append(_finding("large_response", f"{call.tool} returned {call.response_bytes} bytes.", [call], severity="info"))

    from .telemetry_missing import find_missing_fields

    for item in find_missing_fields(flow, final_answer):
        if item["verdict"] == "missing_field":
            reason = f"{item['followUp']} after {item['after']} supplied fields that were then used: {item['confirmed']}"
            severity = "warning"
        else:
            reason = f"{item['followUp']} after {item['after']} but none of its extra fields were used (routing/wording)."
            severity = "candidate"
        findings.append({"code": item["verdict"], "severity": severity, "reason": reason, "traceIds": item["traceIds"]})

    return findings
