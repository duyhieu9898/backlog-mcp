#!/usr/bin/env python3
from .client import BacklogClient
from .resolver import (
    find_option,
    resolve_assignee,
    resolve_category,
    resolve_custom_fields,
    resolve_custom_field_defaults,
    resolve_issue_type,
    resolve_status,
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


def build_create_payload(
    config,
    summary_or_args=None,
    issue_type: str | None = None,
    project_key: str = "",
    parent_key: str = "",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    category: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours=None,
    actual_hours=None,
    custom_fields=None,
    workspace_path=None,
):
    if hasattr(summary_or_args, "summary"):
        args = summary_or_args
        summary = getattr(args, "summary", "")
        issue_type = getattr(args, "issue_type", None)
        project_key = getattr(args, "project", "")
        parent_key = getattr(args, "parent", "")
        description = getattr(args, "desc", "")
        priority = getattr(args, "priority", "")
        assignee = getattr(args, "assignee", "")
        category = getattr(args, "category", "")
        start_date = getattr(args, "start_date", "")
        due_date = getattr(args, "due_date", "")
        estimated_hours = getattr(args, "estimated_hours", None)
        actual_hours = getattr(args, "actual_hours", None)
        custom_fields = getattr(args, "custom", None)
        workspace_path = getattr(args, "workspace_path", None)
    else:
        summary = summary_or_args

    if not issue_type:
        raise ValueError("--issue-type is required for generic create. Use workflow scripts for business defaults.")

    project = resolve_project(config, project_key or None, start_path=workspace_path)
    defaults = config.get("defaults", {})
    _priority = priority or defaults.get("priority_id", 3)
    _assignee = assignee or defaults.get("assignee")
    client = BacklogClient(config)

    data: dict = {
        "projectId": client.get_project_id(project),
        "summary": summary,
        "issueTypeId": resolve_issue_type(project, issue_type),
        "priorityId": resolve_priority(config, _priority),
    }

    optional_values = {
        "description": description or None,
        "assigneeId": resolve_assignee(config, _assignee) if _assignee else None,
        "parentIssueId": resolve_parent_issue_id(config, parent_key) if parent_key else None,
        "startDate": start_date or None,
        "dueDate": due_date or None,
        "estimatedHours": estimated_hours,
        "actualHours": actual_hours,
    }
    data.update({k: v for k, v in optional_values.items() if v is not None})

    if category:
        category_id = resolve_category(project, category)
        if category_id:
            data["categoryId[]"] = [category_id]

    if custom_fields:
        if isinstance(custom_fields, dict):
            data.update(resolve_custom_field_defaults(project, custom_fields))
        elif isinstance(custom_fields, (list, tuple)):
            data.update(resolve_custom_fields(project, custom_fields))

    return data


def create_issue(
    config,
    summary,
    issue_type: str = "",
    project_key: str = "",
    parent_key: str = "",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    category: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours=None,
    actual_hours=None,
    custom_fields: dict | None = None,
    dry_run: bool = True,
    workspace_path=None,
):
    """Create a Backlog issue.

    Returns the created issue dict, or a dry-run preview when dry_run=True.
    custom_fields: dict mapping configured field keys to values,
                   e.g. {'qc_activity': 'Unit Test'}.
    """
    if hasattr(summary, "summary"):
        args = summary
        data = build_create_payload(config, args)
        dry_run = getattr(args, "dry_run", dry_run)
        project = resolve_project(config, getattr(args, "project", None), start_path=getattr(args, "workspace_path", None))
    else:
        data = build_create_payload(
            config,
            summary_or_args=summary,
            issue_type=issue_type,
            project_key=project_key,
            parent_key=parent_key,
            description=description,
            priority=priority,
            assignee=assignee,
            category=category,
            start_date=start_date,
            due_date=due_date,
            estimated_hours=estimated_hours,
            actual_hours=actual_hours,
            custom_fields=custom_fields,
            workspace_path=workspace_path,
        )
        project = resolve_project(config, project_key or None, start_path=workspace_path)

    if dry_run:
        log_event("info", "dry_run", command="create", project=project.get("key"),
                  payload_keys=",".join(sorted(data.keys())))
        return {"dryRun": True, "payload": data}

    return BacklogClient(config).create_issue(data)


def build_update_payload(
    config,
    issue_id_or_args=None,
    project_key: str = "",
    summary: str = "",
    status: str = "",
    comment: str = "",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    category: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours=None,
    actual_hours=None,
    custom_fields: dict | None = None,
    workspace_path=None,
):
    if hasattr(issue_id_or_args, "issue_id"):
        args = issue_id_or_args
        issue_id = getattr(args, "issue_id", "")
        project_key = getattr(args, "project", "")
        summary = getattr(args, "summary", "")
        status = getattr(args, "status", "")
        comment = getattr(args, "comment", "")
        description = getattr(args, "desc", "")
        priority = getattr(args, "priority", "")
        assignee = getattr(args, "assignee", "")
        category = getattr(args, "category", "")
        start_date = getattr(args, "start_date", "")
        due_date = getattr(args, "due_date", "")
        estimated_hours = getattr(args, "estimated_hours", None)
        actual_hours = getattr(args, "actual_hours", None)
        custom_fields = getattr(args, "custom", None)
        workspace_path = getattr(args, "workspace_path", None)
    else:
        issue_id = issue_id_or_args

    project = resolve_project_for_issue(
        config, issue_id, project_key or None, start_path=workspace_path
    )

    data: dict = {}
    optional_values = {
        "summary": summary or None,
        "description": description or None,
        "statusId": resolve_status(project, status) if status else None,
        "priorityId": resolve_priority(config, priority) if priority else None,
        "assigneeId": resolve_assignee(config, assignee) if assignee else None,
        "startDate": start_date or None,
        "dueDate": due_date or None,
        "estimatedHours": estimated_hours,
        "actualHours": actual_hours,
        "comment": comment or None,
    }
    data.update({k: v for k, v in optional_values.items() if v is not None})

    if category:
        category_id = resolve_category(project, category)
        if category_id:
            data["categoryId[]"] = [category_id]

    if custom_fields:
        if isinstance(custom_fields, dict):
            data.update(resolve_custom_field_defaults(project, custom_fields))
        elif isinstance(custom_fields, (list, tuple)):
            data.update(resolve_custom_fields(project, custom_fields))

    if not data:
        raise ValueError("No update fields provided.")
    return data


def update_issue(
    config,
    issue_id,
    project_key: str = "",
    summary: str = "",
    status: str = "",
    comment: str = "",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    category: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours=None,
    actual_hours=None,
    custom_fields: dict | None = None,
    dry_run: bool = True,
    workspace_path=None,
):
    """Update a Backlog issue.

    Returns the updated issue dict, or a dry-run preview when dry_run=True.
    Only non-empty / non-None fields are sent to the API.
    custom_fields: dict mapping configured field keys to values.
    """
    if hasattr(issue_id, "issue_id"):
        args = issue_id
        data = build_update_payload(config, args)
        dry_run = getattr(args, "dry_run", dry_run)
        project = resolve_project_for_issue(
            config, args.issue_id, getattr(args, "project", None),
            start_path=getattr(args, "workspace_path", None)
        )
        target_id = args.issue_id
    else:
        data = build_update_payload(
            config,
            issue_id_or_args=issue_id,
            project_key=project_key,
            summary=summary,
            status=status,
            comment=comment,
            description=description,
            priority=priority,
            assignee=assignee,
            category=category,
            start_date=start_date,
            due_date=due_date,
            estimated_hours=estimated_hours,
            actual_hours=actual_hours,
            custom_fields=custom_fields,
            workspace_path=workspace_path,
        )
        project = resolve_project_for_issue(
            config, issue_id, project_key or None, start_path=workspace_path
        )
        target_id = issue_id

    if dry_run:
        log_event("info", "dry_run", command="update", project=project.get("key"),
                  issue=target_id, payload_keys=",".join(sorted(data.keys())))
        return {"dryRun": True, "issue": target_id, "payload": data}

    return BacklogClient(config).update_issue(target_id, data)
