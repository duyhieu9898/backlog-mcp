#!/usr/bin/env python3
import re

from backlog_tool.presenter import compact_issue, user_name

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


COMMENT_TEXT_LIMIT = 2000


def comment_text(comment):
    return (comment.get("content") or "").strip()


def comment_summary(comment):
    text = comment_text(comment)
    summary = {
        "author": user_name(comment.get("createdUser")),
        "created": comment.get("created"),
        "content": text if len(text) <= COMMENT_TEXT_LIMIT else text[:COMMENT_TEXT_LIMIT] + "…",
    }
    changes = [
        f"{change.get('field')}: {change.get('originalValue') or '-'} -> {change.get('newValue') or '-'}"
        for change in comment.get("changeLog") or []
        if change.get("field") != "notification"
    ]
    if changes:
        summary["changes"] = changes
    return summary


def handoff_comment(comments, assignee):
    """The comment written when the issue was last assigned to its current assignee: QC reopening
    with what is still missing, or a teammate handing the work over. None when that assignment
    came without text, so an older handoff never stands in for the current one."""
    if not assignee:
        return None
    for comment in sorted(comments, key=lambda c: c.get("created") or "", reverse=True):
        if any(
            change.get("field") == "assigner" and change.get("newValue") == assignee
            for change in comment.get("changeLog") or []
        ):
            return comment_summary(comment) if comment_text(comment) else None
    return None


def issue_context(issue, base_url="", comments=None, include_comments=False, handoff=True):
    """One issue as the model reads it. A bug report written in the template comes back as
    parsed sections; any other description comes back as text. With comments, it carries the count
    of written comments and, when handoff (the issue is the caller's to work on), the handoff comment;
    include_comments adds them all, oldest first."""
    compact = compact_issue(issue, base_url=base_url)
    context = {k: v for k, v in compact.items() if k not in ("description", "resourceUri", "customFields")}
    creator = user_name(issue.get("createdUser"))
    if creator:
        context["createdUser"] = creator
    text = compact.get("description")
    sections = parse_bug_description(text)
    meta = bug_description_metadata(sections)
    if meta["hasTemplateMarkers"]:
        context["description"] = {k: v for k, v in sections.items() if v}
        context["descriptionMeta"] = meta
        # The sections carry the whole text unless some are missing; only then is the raw text needed.
        if meta["missingSections"]:
            context["rawDescription"] = text
    elif text:
        context["description"] = text
    if compact.get("customFields"):
        context["customFields"] = compact["customFields"]
    attachments = attachment_summary(issue.get("attachments"))
    if attachments:
        context["attachments"] = attachments
    if comments is not None:
        written = sorted((c for c in comments if comment_text(c)), key=lambda c: c.get("created") or "")
        context["commentCount"] = len(written)
        latest = handoff_comment(comments, context.get("assignee")) if handoff else None
        if latest:
            context["handoffComment"] = latest
        if include_comments and written:
            context["comments"] = [comment_summary(c) for c in written]
    return context
