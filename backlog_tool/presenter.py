#!/usr/bin/env python3
"""Compact presenters shared by every CLI command.

Default output is trimmed to the fields needed to triage/act, which is the main
token-cost lever. Pass --json-full at the CLI to bypass this and get raw JSON.
"""
import re
from collections import Counter

def _attachment_url(attachment_id, base_url=""):
    """Build a full attachment image URL."""
    base = (base_url or "").rstrip("/")
    return f"{base}/ViewAttachmentImage.action?attachmentId={attachment_id}"


def _build_attachment_map(attachments, base_url=""):
    """Map filename -> full URL from attachments list."""
    mapping = {}
    for att in attachments or []:
        name = att.get("name")
        att_id = att.get("id")
        if name and att_id:
            mapping[name] = _attachment_url(att_id, base_url=base_url)
    return mapping


def _replace_evidence_urls(description, attachments, base_url=""):
    """Replace ![image][filename] references in description with full URLs."""
    if not description or not attachments:
        return description
    mapping = _build_attachment_map(attachments, base_url=base_url)
    if not mapping:
        return description

    def replacer(match):
        filename = match.group(1)
        url = mapping.get(filename)
        if url:
            return url
        return match.group(0)

    # Pattern: ![image][filename] or ![alt][filename]
    return re.sub(r"!\[[^\]]*\]\[([^\]]+)\]", replacer, description)


def user_name(user):
    return (user or {}).get("name") if user else None


def compact_custom_value(value):
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, list):
        return [(v or {}).get("name", v) if isinstance(v, dict) else v for v in value]
    return value


def compact_custom_fields(custom_fields):
    """Only include custom fields that have a meaningful value."""
    result = []
    for field in custom_fields or []:
        value = compact_custom_value(field.get("value"))
        if _has_value(value):
            result.append({"name": field.get("name"), "value": value})
    return result


def _has_value(value):
    """Check if a custom field value is meaningful (not null/empty/'-')."""
    if value is None:
        return False
    if value == "-":
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


from datetime import date, datetime


def parse_due_date(value):
    if not value:
        return None
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def due_status(due_date, today=None):
    if today is None:
        today = date.today()
    if due_date is None:
        return {
            "daysUntilDue": None,
            "dueAlertLevel": None,
        }
    days_until_due = (due_date - today).days
    if days_until_due < 0:
        alert_level = 1
    elif days_until_due < 2:
        alert_level = 2
    else:
        alert_level = None
    return {
        "daysUntilDue": days_until_due,
        "dueAlertLevel": alert_level,
    }


def compact_issue(issue, view="compact", base_url=""):
    """Trim a raw Backlog issue (get/create/update/apply response)."""
    if not isinstance(issue, dict):
        return issue
    if view == "full":
        return issue

    base_url = (base_url or "").rstrip("/")

    description = issue.get("description")
    attachments = issue.get("attachments")
    if description and attachments:
        description = _replace_evidence_urls(description, attachments, base_url=base_url)
        
    issue_key = issue.get("issueKey")
    
    fields = {
        "issueKey": issue_key,
        "summary": issue.get("summary"),
        "description": description,
        "issueType": (issue.get("issueType") or {}).get("name") if isinstance(issue.get("issueType"), dict) else issue.get("issueType"),
        "status": (issue.get("status") or {}).get("name") if isinstance(issue.get("status"), dict) else issue.get("status"),
        "assignee": user_name(issue.get("assignee")) if isinstance(issue.get("assignee"), dict) else issue.get("assignee"),
        "priority": (issue.get("priority") or {}).get("name") if isinstance(issue.get("priority"), dict) else issue.get("priority"),
        "startDate": issue.get("startDate"),
        "dueDate": issue.get("dueDate"),
        "estimatedHours": issue.get("estimatedHours"),
        "actualHours": issue.get("actualHours"),
        "resourceUri": f"backlog://issue/{issue_key}" if issue_key else None,
        "url": f"{base_url}/view/{issue_key}" if (base_url and issue_key) else None,
    }
    
    custom = compact_custom_fields(issue.get("customFields"))
    # Drop fields with no value to reduce noise
    result = {k: v for k, v in fields.items() if v is not None}
    if custom:
        result["customFields"] = custom
    return result


# A personal list is for picking work: the assignee is always the caller, the description
# comes from get_issue, and the custom fields are resolve_bug's business.
_LIST_ITEM_DROPPED = {"description", "assignee", "customFields", "resourceUri"}


def list_item(issue, base_url="", today=None):
    """One row of an issue list: the fields to pick an issue by, plus due-date context."""
    item = {k: v for k, v in compact_issue(issue, base_url=base_url).items() if k not in _LIST_ITEM_DROPPED}
    due = due_status(parse_due_date(issue.get("dueDate")), today)
    item.update({k: v for k, v in due.items() if v is not None})
    return item


def _named(key):
    return lambda issue: (issue.get(key) or {}).get("name")


def _date(key):
    return lambda issue: str(issue[key]).split("T", 1)[0] if issue.get(key) else None


# Issue fields a create/update can write, in the order changes are reported.
_CHANGE_FIELDS = [
    ("Summary", lambda issue: issue.get("summary")),
    ("Issue Type", _named("issueType")),
    ("Status", _named("status")),
    ("Priority", _named("priority")),
    ("Assignee", lambda issue: user_name(issue.get("assignee"))),
    ("Category", lambda issue: [c.get("name") for c in issue.get("category") or []] or None),
    ("Start Date", _date("startDate")),
    ("Due Date", _date("dueDate")),
    ("Estimated Hours", lambda issue: issue.get("estimatedHours")),
    ("Actual Hours", lambda issue: issue.get("actualHours")),
    ("Description", lambda issue: issue.get("description") or None),
]


def issue_changes(before, after, comment=None):
    """What a write did, as {field, from, to} by display name; before is None for a new issue."""
    before = before or {}
    changes = []
    for label, read in _CHANGE_FIELDS:
        old, new = read(before), read(after)
        if old != new:
            changes.append({"field": label, "from": old, "to": new})
    old_custom = {f.get("id"): compact_custom_value(f.get("value")) for f in before.get("customFields") or []}
    for field in after.get("customFields") or []:
        old = old_custom.get(field.get("id"))
        new = compact_custom_value(field.get("value"))
        if old != new and (_has_value(old) or _has_value(new)):
            changes.append({"field": field.get("name"), "from": old if _has_value(old) else None, "to": new})
    if comment:
        changes.append({"field": "Comment", "from": None, "to": comment})
    return changes


def list_summary(items):
    return {
        "byType": dict(Counter(item.get("issueType") for item in items)),
        "overdueCount": sum(1 for item in items if item.get("dueAlertLevel") == 1),
        "dueSoonCount": sum(1 for item in items if item.get("dueAlertLevel") == 2),
    }


def format_issues_as_table(issues, is_story_view=False):
    if not issues:
        return "No issues found."

    # Ensure all elements are dicts
    issues = [item for item in issues if isinstance(item, dict)]
    if not issues:
        return "No issues found."

    if is_story_view:
        headers = ["Key", "Summary", "Status", "Due Date", "Days Left", "Alert"]
        rows = []
        for issue in issues:
            due_date = issue.get("dueDate", "") or ""
            if due_date and "T" in due_date:
                due_date = due_date.split("T")[0]

            alert = ""
            alert_level = issue.get("dueAlertLevel")
            if alert_level == 1:
                alert = "⚠️ Overdue"
            elif alert_level == 2:
                alert = "🕒 Due Soon"

            rows.append([
                issue.get("issueKey") or "",
                issue.get("summary") or "",
                issue.get("status") or "",
                due_date,
                str(issue.get("daysUntilDue")) if issue.get("daysUntilDue") is not None else "",
                alert
            ])
    else:
        headers = ["Key", "Summary", "Type", "Status", "Assignee", "Priority", "Due Date"]
        rows = []
        for issue in issues:
            due_date = issue.get("dueDate", "") or ""
            if due_date and "T" in due_date:
                due_date = due_date.split("T")[0]
            rows.append([
                issue.get("issueKey") or "",
                issue.get("summary") or "",
                issue.get("issueType") or "",
                issue.get("status") or "",
                issue.get("assignee") or "",
                issue.get("priority") or "",
                due_date
            ])

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    # Build the markdown table
    lines = []
    lines.append("| " + " | ".join(str(val).ljust(widths[i]) for i, val in enumerate(headers)) + " |")
    lines.append("|-" + "-|-".join("-" * widths[i] for i in range(len(headers))) + "-|")
    for row in rows:
        lines.append("| " + " | ".join(str(val).ljust(widths[i]) for i, val in enumerate(row)) + " |")

    return "\n".join(lines)
