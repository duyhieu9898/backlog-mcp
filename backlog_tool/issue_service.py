#!/usr/bin/env python3
from .client import BacklogClient
from .resolver import (
    find_option,
    resolve_assignee,
    resolve_category,
    resolve_custom_fields,
    resolve_issue_type,
)
from .settings import log_event, resolve_project, resolve_project_for_issue


def request_json(config, method, path, data=None):
    return BacklogClient(config).request_json(method, path, data=data)


def resolve_priority(config, selected):
    if selected is None:
        return None
    if str(selected).isdigit():
        return int(selected)
    priorities = request_json(config, "GET", "/priorities")
    return find_option(priorities, selected, "priority")


def resolve_status(config, project, selected):
    if selected is None:
        return None
    if str(selected).isdigit():
        return int(selected)
    statuses = request_json(config, "GET", f"/projects/{project['key']}/statuses")
    return find_option(statuses, selected, "status")


def resolve_parent_issue_id(config, parent_issue_key):
    if not parent_issue_key:
        return None
    issue = request_json(config, "GET", f"/issues/{parent_issue_key}")
    return issue["id"]


def get_issue(config, issue_id):
    return BacklogClient(config).get_issue(issue_id)


def get_issues(
    config,
    project_key=None,
    query=None,
    assignee_id=None,
    open_only=False,
    issue_types=None,
    limit=100,
    offset=0,
    sort=None,
    order=None,
    start_path=None,
):
    """List issues with optional filters.

    open_only: exclude Closed status via API filter.
    issue_types: list of type names (e.g. ["Bug", "Story"]) to filter.
    """
    project = resolve_project(config, project_key, start_path=start_path)
    client = BacklogClient(config)
    project_id = client.get_project_id(project)

    status_ids = None
    if open_only:
        status_ids = _non_closed_status_ids(project)

    issue_type_ids = None
    if issue_types:
        issue_type_ids = _resolve_issue_type_ids(project, issue_types)

    return client.get_issues(
        project_id, query=query, assignee_id=assignee_id,
        status_ids=status_ids, issue_type_ids=issue_type_ids,
        count=limit, offset=offset, sort=sort, order=order,
    )


def _non_closed_status_ids(project):
    """Get all status IDs except Closed."""
    statuses = project.get("bug", {}).get("status_options", [])
    return [s["id"] for s in statuses if s.get("name") != "Closed"]


def _resolve_issue_type_ids(project, type_names):
    """Resolve issue type names to IDs from project catalog."""
    options = project.get("bug", {}).get("issue_type_options", [])
    name_set = set(type_names)
    ids = [opt["id"] for opt in options if opt.get("name") in name_set]
    if not ids:
        available = ", ".join(opt["name"] for opt in options)
        raise ValueError(f"Unknown issue type(s): {type_names}. Available: {available}")
    return ids


def build_create_payload(config, args):
    project = resolve_project(config, args.project, start_path=getattr(args, "workspace_path", None))
    defaults = config.get("defaults", {})
    issue_type = args.issue_type
    if issue_type is None:
        raise ValueError("--issue-type is required for generic create. Use workflow scripts for business defaults.")
    priority = args.priority or defaults.get("priority_id", 3)
    assignee = args.assignee or defaults.get("assignee")
    client = BacklogClient(config)

    data = {
        "projectId": client.get_project_id(project),
        "summary": args.summary,
        "issueTypeId": resolve_issue_type(project, issue_type),
        "priorityId": resolve_priority(config, priority),
    }
    optional_values = {
        "description": args.desc,
        "assigneeId": resolve_assignee(config, assignee),
        "parentIssueId": resolve_parent_issue_id(config, args.parent),
        "startDate": args.start_date,
        "dueDate": args.due_date,
        "estimatedHours": args.estimated_hours,
        "actualHours": args.actual_hours,
    }
    data.update({key: value for key, value in optional_values.items() if value is not None})

    category_id = resolve_category(project, args.category)
    if category_id:
        data["categoryId[]"] = [category_id]
    data.update(resolve_custom_fields(project, args.custom))
    return data


def create_issue(config, args):
    data = build_create_payload(config, args)
    if args.dry_run:
        log_event("info", "dry_run", command="create", project=args.project, payload_keys=",".join(sorted(data.keys())))
        return {"dryRun": True, "payload": data}
    return BacklogClient(config).create_issue(data)


def build_update_payload(config, args):
    project = resolve_project_for_issue(config, args.issue_id, args.project, start_path=getattr(args, "workspace_path", None))
    data = {}
    optional_values = {
        "summary": args.summary,
        "description": args.desc,
        "statusId": resolve_status(config, project, args.status),
        "priorityId": resolve_priority(config, args.priority),
        "assigneeId": resolve_assignee(config, args.assignee),
        "startDate": args.start_date,
        "dueDate": args.due_date,
        "estimatedHours": args.estimated_hours,
        "actualHours": args.actual_hours,
        "comment": args.comment,
    }
    data.update({key: value for key, value in optional_values.items() if value is not None})

    category_id = resolve_category(project, args.category)
    if category_id:
        data["categoryId[]"] = [category_id]
    data.update(resolve_custom_fields(project, args.custom))
    if not data:
        raise ValueError("No update fields provided.")
    return data


def update_issue(config, args):
    data = build_update_payload(config, args)
    if args.dry_run:
        log_event(
            "info",
            "dry_run",
            command="update",
            project=args.project,
            issue=args.issue_id,
            payload_keys=",".join(sorted(data.keys())),
        )
        return {"dryRun": True, "issue": args.issue_id, "payload": data}
    return BacklogClient(config).update_issue(args.issue_id, data)
