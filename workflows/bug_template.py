#!/usr/bin/env python3
import re

from backlog_tool.presenter import compact_custom_fields

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


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")


def attachment_summary(attachments):
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "size": item.get("size"),
            "isImage": str(item.get("name") or "").lower().endswith(IMAGE_EXTENSIONS),
        }
        for item in attachments or []
        if isinstance(item, dict)
    ]


def bug_context(issue, base_url=""):
    description = parse_bug_description(issue.get("description"))
    meta = bug_description_metadata(description)
    base_url = (base_url or "").rstrip("/")
    context = {
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
        "descriptionMeta": meta,
        "customFields": compact_custom_fields(issue.get("customFields")),
    }
    # The parsed sections carry the whole text unless some are missing; only then is the raw text needed.
    if meta["missingSections"]:
        context["rawDescription"] = issue.get("description")
    if base_url and issue.get("issueKey"):
        context["url"] = f"{base_url}/view/{issue['issueKey']}"
    attachments = attachment_summary(issue.get("attachments"))
    if attachments:
        context["attachments"] = attachments
    return context
