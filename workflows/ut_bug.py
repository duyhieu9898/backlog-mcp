#!/usr/bin/env python3
from datetime import datetime, timedelta
from copy import deepcopy

from backlog_tool.client import BacklogClient
from backlog_tool.resolver import (
    category_options,
    find_option,
    issue_type_options,
    resolve_custom_field_defaults,
    resolve_status,
)

from backlog_tool.settings import load_workflow_config, log_event, resolve_project, resolve_user_id
from .config import require_int, require_mapping, require_value


class PostCreateUpdateError(RuntimeError):
    def __init__(self, issue_key, payload, target_status, error):
        super().__init__(
            f"Created UT bug {issue_key}, but failed to update it to {target_status}. "
            f"Run manually: python3 scripts/backlog.py issue update {issue_key} "
            f"--status {target_status} --assignee <creator-or-me> --apply. Error: {error}"
        )
        self.issue_key = issue_key
        self.payload = payload
        self.target_status = target_status
        self.error = error


def require_bug_config(project):
    return project.get("bug") or {}


def merge_bug_defaults(config, project_key):
    workflow = load_workflow_config("ut_bug")
    merged = {key: deepcopy(value) for key, value in workflow.items() if key != "project_overrides"}
    override = workflow.get("project_overrides", {}).get(project_key, {})
    merged.update(override)
    merged["custom_fields"] = {
        **workflow.get("custom_fields", {}),
        **override.get("custom_fields", {}),
    }
    return merged


def build_subtask_bug_payload(config, project_key, parent_key, module, description, start_path=None):
    project = resolve_project(config, project_key, start_path=start_path)
    project_key = project["key"]
    bug = require_bug_config(project)
    bug_defaults = merge_bug_defaults(config, project_key)
    defaults = config.get("defaults", {})
    assignee_id = resolve_user_id(config, require_value(defaults, "assignee", "config.defaults"))
    client = BacklogClient(config)

    parent_issue = client.get_issue(parent_key)
    parent_id = parent_issue["id"]

    today = datetime.now()
    due_date = today + timedelta(days=require_int(bug_defaults, "due_in_days", "ut_bug"))
    summary = f"[{parent_key}][{module}] {description}"

    corrective_action_template = require_value(bug_defaults, "corrective_action", "ut_bug")
    corrective_action = corrective_action_template.format(
        description=description,
        description_lower=description.lower(),
    )

    issue_type_id = find_option(
        issue_type_options(project),
        require_value(bug_defaults, "issue_type", "ut_bug"),
        "issue type",
    )
    if not issue_type_id:
        raise ValueError(f"Missing issue_type in ut_bug workflow config for project {project_key}")
    category_id = find_option(
        category_options(project),
        bug_defaults.get("category"),
        "category",
    )
    status_id = resolve_status(project, require_value(bug_defaults, "status", "ut_bug"))
    target_status = require_value(bug_defaults, "status", "ut_bug")

    data = {
        "projectId": client.get_project_id(project),
        "summary": summary,
        "description": require_value(bug_defaults, "description_template", "ut_bug"),
        "parentIssueId": parent_id,
        "issueTypeId": issue_type_id,
        "priorityId": require_value(defaults, "priority_id", "config.defaults"),
        "assigneeId": assignee_id,
        "startDate": today.strftime("%Y-%m-%d"),
        "dueDate": due_date.strftime("%Y-%m-%d"),
        "estimatedHours": require_value(bug_defaults, "estimated_hours", "ut_bug"),
        "actualHours": require_value(bug_defaults, "actual_hours", "ut_bug"),
    }
    if category_id:
        data["categoryId[]"] = [category_id]
    data.update(resolve_custom_field_defaults(project, require_mapping(bug_defaults, "custom_fields", "ut_bug")))

    corrective_action_config = bug.get("custom_fields", {}).get("corrective_action")
    if corrective_action_config:
        data[corrective_action_config["field"]] = corrective_action

    return {
        "project": project_key,
        "parentIssueKey": parent_key,
        "parentIssueId": parent_id,
        "payload": data,
        "postCreatePayload": {
            "statusId": status_id,
            "assigneeId": assignee_id,
        },
        "targetStatus": target_status,
}


def require_created_issue(response):
    issue_key = response.get("issueKey")
    if not issue_key:
        raise ValueError("Backlog create issue response is missing issueKey.")
    return issue_key


def created_user_id(response):
    created_user = response.get("createdUser") or {}
    user_id = created_user.get("id")
    return int(user_id) if user_id else None


def create_subtask_bug(config, project_key, parent_key, module, description, dry_run=False, start_path=None):
    built = build_subtask_bug_payload(config, project_key, parent_key, module, description, start_path=start_path)
    if dry_run:
        log_event(
            "info",
            "dry_run",
            command="ut_bug",
            project=built["project"],
            parent_issue=parent_key,
            payload_keys=",".join(sorted(built["payload"].keys())),
        )
        return {"dryRun": True, **built}

    client = BacklogClient(config)
    created = client.create_issue(built["payload"])
    issue_key = require_created_issue(created)
    close_payload = dict(built["postCreatePayload"])
    user_id = created_user_id(created)
    if user_id:
        close_payload["assigneeId"] = user_id
    try:
        updated = client.update_issue(issue_key, close_payload)
    except Exception as error:
        raise PostCreateUpdateError(
            issue_key,
            close_payload,
            built["targetStatus"],
            error,
        ) from error
    return {
        "issueKey": updated.get("issueKey") or issue_key,
        "created": created,
        "updated": updated,
        "postCreatePayload": close_payload,
    }
