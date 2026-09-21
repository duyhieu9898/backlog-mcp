from datetime import date, datetime

from backlog_tool.client import BacklogClient
from backlog_tool.settings import load_workflow_config, resolve_project, resolve_user_id
from .config import require_list, require_value


def issue_type_name(issue):
    return (issue.get("issueType") or {}).get("name")


def status_name(issue):
    return (issue.get("status") or {}).get("name")


def user_id(user):
    return (user or {}).get("id")


def is_story_or_task_for_user(issue, assignee_id, issue_types, excluded_statuses):
    if issue_type_name(issue) not in issue_types:
        return False
    if status_name(issue) in excluded_statuses:
        return False
    return user_id(issue.get("assignee")) == assignee_id


def parse_due_date(value):
    if not value:
        return None
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[0]
    return datetime.strptime(text, "%Y-%m-%d").date()


def due_status(due_date, today):
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


def summarize_story_task(issue, today):
    due_date = parse_due_date(issue.get("dueDate"))
    return {
        "issueKey": issue.get("issueKey"),
        "summary": issue.get("summary"),
        "description": issue.get("description"),
        "status": status_name(issue),
        "dueDate": issue.get("dueDate"),
        **due_status(due_date, today),
    }


def my_story_task_overview(
    config,
    project_key=None,
    query=None,
    today=None,
    limit=100,
    offset=0,
    sort=None,
    order=None,
    start_path=None,
):
    workflow = load_workflow_config("story_task_overview")
    project = resolve_project(config, project_key, start_path=start_path)
    assignee_id = resolve_user_id(config, require_value(workflow, "assignee", "story_task_overview"))
    issue_types = set(require_list(workflow, "issue_types", "story_task_overview"))
    excluded_statuses = set(require_list(workflow, "excluded_statuses", "story_task_overview"))
    fields = require_list(workflow, "fields", "story_task_overview")
    today = today or date.today()

    client = BacklogClient(config)
    issues = client.get_issues(
        client.get_project_id(project),
        query=query,
        assignee_id=assignee_id,
        count=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    return [
        {
            field: summary.get(field)
            for field in fields
        }
        for issue in issues
        if is_story_or_task_for_user(issue, assignee_id, issue_types, excluded_statuses)
        for summary in [summarize_story_task(issue, today)]
    ]
