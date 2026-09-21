#!/usr/bin/env python3
import re

BUG_TEMPLATE_SECTIONS = [
    ("environment", "Environment"),
    ("pre_condition", "Pre-Condition"),
    ("steps_to_reproduce", "Steps to reproduce"),
    ("actual", "Actual"),
    ("expected", "Expected"),
    ("evidence", "Evidence"),
]

SECTION_PATTERN = re.compile(
    r"(?im)^\s*\*\*(Environment|Pre-Condition|Steps to reproduce|Actual|Expected|Evidence)(?:\*\*)?:(?:\*\*)?\s*(.*)$"
)


def clean_inline_value(value):
    return (value or "").strip().removesuffix("**").strip()


def parse_bug_description(description):
    text = description or ""
    parsed = {key: "" for key, _label in BUG_TEMPLATE_SECTIONS}
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return parsed

    label_to_key = {label: key for key, label in BUG_TEMPLATE_SECTIONS}
    for index, match in enumerate(matches):
        label = match.group(1)
        inline_value = clean_inline_value(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        parsed[label_to_key[label]] = "\n".join(part for part in [inline_value, body] if part).strip()
    return parsed


def bug_description_metadata(parsed):
    present = [key for key, value in parsed.items() if value]
    missing = [key for key, _label in BUG_TEMPLATE_SECTIONS if not parsed.get(key)]
    return {
        "hasTemplateMarkers": bool(present),
        "presentSections": present,
        "missingSections": missing,
    }


def compact_user(user):
    user = user or {}
    return {
        key: user.get(key)
        for key in ("id", "name", "roleType")
        if user.get(key) is not None
    }


def bug_context(issue):
    description = parse_bug_description(issue.get("description"))
    return {
        "issueKey": issue.get("issueKey"),
        "summary": issue.get("summary"),
        "status": (issue.get("status") or {}).get("name"),
        "assignee": compact_user(issue.get("assignee")),
        "createdUser": compact_user(issue.get("createdUser")),
        "startDate": issue.get("startDate"),
        "dueDate": issue.get("dueDate"),
        "estimatedHours": issue.get("estimatedHours"),
        "actualHours": issue.get("actualHours"),
        "description": description,
        "descriptionMeta": bug_description_metadata(description),
        "rawDescription": issue.get("description"),
        "customFields": issue.get("customFields", []),
    }
