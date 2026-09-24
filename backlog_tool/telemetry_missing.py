"""Detect fields a specialized tool did not return but the model fetched with a follow-up call and then used."""

import json
import re

from .telemetry_rules import SPECIALIZED

MIN_TEXT_LENGTH = 4
MIN_NUMBER_DIGITS = 3


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for child in value:
            yield from _leaves(child, f"{prefix}[]")
    else:
        yield prefix, value


def _paths(value):
    return {path for path, _ in _leaves(value)}


def _used(value, haystack):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        text = str(value)
        if sum(ch.isdigit() for ch in text) < MIN_NUMBER_DIGITS:
            return False
        return re.search(rf"(?<!\d){re.escape(text)}(?!\d)", haystack) is not None
    text = str(value)
    return len(text) >= MIN_TEXT_LENGTH and text.lower() in haystack.lower()


def find_missing_fields(flow, final_answer=None):
    specialized_for = {generic: special for generic, special in SPECIALIZED}
    findings = []
    calls = flow.calls
    for i, follow_up in enumerate(calls):
        special = specialized_for.get(follow_up.tool)
        if not special:
            continue
        earlier = [c for c in calls[:i] if c.tool == special and c.issue_key == follow_up.issue_key]
        if not earlier or follow_up.result is None:
            continue
        first = earlier[-1]
        candidates = sorted(_paths(follow_up.result) - _paths(first.result))
        haystack = " ".join(
            [json.dumps(c.arguments, ensure_ascii=False) for c in calls[i + 1:]] + [final_answer or ""]
        )
        values = {}
        for path, value in _leaves(follow_up.result):
            if path in candidates:
                values.setdefault(path, []).append(value)
        confirmed = sorted(path for path, items in values.items() if any(_used(v, haystack) for v in items))
        findings.append({
            "after": first.tool,
            "followUp": follow_up.tool,
            "confirmed": confirmed,
            "candidates": candidates,
            "verdict": "missing_field" if confirmed else "routing",
            "traceIds": [first.trace_id, follow_up.trace_id],
        })
    return findings
