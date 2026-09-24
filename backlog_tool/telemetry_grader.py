"""Tier-3: scenario definitions, real-prompt matching, and grading a flow against expectations."""

import copy
import json
import os
import re

from . import settings

SCENARIOS_PATH = os.path.join(settings.MCP_ROOT, "evals", "scenarios.json")
ISSUE_KEY_IN_TEXT = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")


def load_scenarios(path=None):
    with open(path or SCENARIOS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _fill(value, fixtures):
    if isinstance(value, str):
        for name, fixture in fixtures.items():
            value = value.replace("{" + name + "}", fixture)
        return value
    if isinstance(value, dict):
        return {k: _fill(v, fixtures) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, fixtures) for v in value]
    return value


def render_scenario(scenario):
    rendered = copy.deepcopy(scenario)
    fixtures = scenario.get("fixtures") or {}
    rendered["prompt"] = _fill(scenario["prompt"], fixtures)
    rendered["expect"] = _fill(scenario["expect"], fixtures)
    return rendered


def match_prompt(prompt, scenarios):
    text = (prompt or "").lower()
    if "backlog" not in text:
        return None
    keys = ISSUE_KEY_IN_TEXT.findall(prompt)
    count = "none" if not keys else ("one" if len(keys) == 1 else "many")
    for scenario in scenarios:
        rule = scenario.get("match")
        if not rule or rule.get("issueKeys") != count:
            continue
        if all(any(word in text for word in group) for group in rule.get("keywords", [])):
            return scenario, keys
    return None


def expect_for(scenario, issue_keys):
    expect = copy.deepcopy(scenario["expect"])
    template = expect["calls"][0]
    if scenario.get("match", {}).get("issueKeys") == "many":
        expect["calls"] = [
            {"tool": template["tool"], "args": {**template["args"], "issue_key": key}} for key in issue_keys
        ]
    elif issue_keys:
        fixtures = {name: issue_keys[0] for name in (scenario.get("fixtures") or {})}
        expect = _fill(expect, fixtures)
    return expect


def _matches(expected, call):
    return expected["tool"] == call.tool and all(call.arguments.get(k) == v for k, v in expected["args"].items())


def grade(expect, flow, final_answer=None, require_final_answer=False):
    calls = [c for c in flow.calls if c.status not in ("invalid_arguments", "rejected")]
    unknown = [c.tool for c in flow.calls if c.status == "rejected"]
    reasons = []

    remaining = list(calls)
    matched = []
    for expected in expect["calls"]:
        index = next((i for i, c in enumerate(remaining) if _matches(expected, c)), None)
        if index is None:
            reasons.append(f"missing expected call {expected['tool']} {expected['args']}")
            continue
        matched.append(remaining.pop(index))
    extra = [c.tool for c in remaining]
    if extra:
        reasons.append(f"extra calls: {extra}")
    if expect.get("order") == "exact" and not extra and matched and [c.trace_id for c in matched] != [c.trace_id for c in calls]:
        reasons.append("calls not in expected order")
    if unknown:
        reasons.append(f"unknown tool calls: {unknown}")

    forbidden = [c.tool for c in flow.calls if c.tool in expect.get("forbidden", [])]
    if forbidden:
        reasons.append(f"forbidden calls: {forbidden}")

    arg_errors = [
        {"tool": c.tool, "unknown": e.get("unknown", [])}
        for c in flow.calls for e in c.errors if e.get("kind") == "arg_error"
    ]
    if arg_errors:
        reasons.append(f"argument errors: {arg_errors}")

    final_check = None
    rule = expect.get("finalAnswer")
    if rule:
        if final_answer is None and require_final_answer:
            final_check = {"missing": "final answer"}
            reasons.append("final answer missing")
        elif final_answer is None:
            final_check = {"skipped": "no final answer"}
        else:
            answer = final_answer.lower()
            # An entry is one phrase, or a list of alternatives of which any one is enough.
            missing = [
                item for item in rule["mustMention"]
                if not any(word.lower() in answer for word in (item if isinstance(item, list) else [item]))
            ]
            final_check = {"missing": missing} if missing else {"ok": True}
            if missing:
                reasons.append(f"final answer does not mention {missing}")

    return {
        "pass": not reasons,
        "reasons": reasons,
        "mcpCalls": [{"tool": c.tool, "arguments": c.arguments, "status": c.status} for c in flow.calls],
        "extraCalls": extra + unknown,
        "forbiddenHits": forbidden,
        "argErrors": arg_errors,
        "finalAnswerCheck": final_check,
        "estTokens": sum(c.est_tokens for c in flow.calls),
    }
