#!/usr/bin/env python3
"""Stdio MCP server exposing the Backlog integration to every local project."""

import json
import os
import time
from typing import Annotated, Any, Literal, Sequence

from pydantic import Field
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from .results import _build_result, _error_result, _pagination, _parse_cursor, _partial_write_result, _resource_uris, _to_markdown

from backlog_tool.settings import (
    load_config,
    load_env_file,
    project_keys,
    load_project_catalog,
    summarize_metrics,
    view_base_url,
)
from backlog_tool import issue_service, presenter
from backlog_tool.resolver import resolve_user_id
from workflows import guidance, ut_bug, story_task_overview
import workflows.resolve_bug as bug_workflow
from workflows.audit import audit_config
from backlog_tool.inspect import build_project_config, write_catalog

IssueView = Literal["compact", "full"]
SortOrder = Literal["asc", "desc"]
MutationMode = Literal["preview", "apply"]
IssueSort = Literal[
    "issueType",
    "category",
    "version",
    "milestone",
    "summary",
    "status",
    "priority",
    "attachment",
    "sharedFile",
    "created",
    "createdUser",
    "updated",
    "updatedUser",
    "assignee",
    "startDate",
    "dueDate",
    "estimatedHours",
    "actualHours",
    "childIssue",
]

SERVER_INSTRUCTIONS = (
    "Use this server for configured Backlog projects. Read before mutating. "
    "Preview mutations first and use apply mode only when the user explicitly requests the write. "
    "When a project is omitted, resolve it from workspace configuration or workspace path only if unambiguous. If the project cannot be resolved confidently, return an error instead of guessing. "
    "Never expose API keys or full request URLs containing query strings."
)

mcp = FastMCP(
    name="Backlog Local",
    instructions=SERVER_INSTRUCTIONS,
    json_response=True,
)

_config: dict[str, Any] | None = None
_bootstrap_error: Exception | None = None


def bootstrap_config() -> dict[str, Any]:
    """Load env and config once at startup."""
    global _config, _bootstrap_error
    load_env_file()
    try:
        _config = load_config()
        _bootstrap_error = None
        return _config
    except Exception as error:
        _config = None
        _bootstrap_error = error
        raise


def get_config_instance() -> dict[str, Any]:
    """Retrieve the singleton config or surface the startup configuration error."""
    global _config, _bootstrap_error
    if _config is not None:
        return _config
    if _bootstrap_error is not None:
        raise RuntimeError(f"Backlog MCP configuration failed to load: {_bootstrap_error}") from _bootstrap_error
    return bootstrap_config()


# Bootstrap on module import
try:
    bootstrap_config()
except Exception:
    # Keep module importable for MCP discovery/tests, but retain the error so
    # the first config-dependent tool call fails clearly instead of retrying silently.
    pass


def _workspace_path() -> str | None:
    """Resolve the active client workspace without exposing it as a tool input."""
    return (
        os.environ.get("BACKLOG_WORKSPACE_PATH")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or None
    )


@mcp.tool()
def get_issue(
    issue_id: Annotated[str, Field(description="Issue key (e.g., 'PROJ-123') or numeric ID")],
    view: Annotated[Literal["compact", "full"], Field(description="Detail level: compact for general triage, full for raw Backlog fields.")] = "compact",
) -> CallToolResult:
    """Get the current details of one Backlog issue by key or numeric ID.

    Use when the user names a specific Backlog issue and you need its current details.
    Do not use when you need to discover multiple issues; use get_issues instead.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        raw_issue = issue_service.get_issue(config, issue_id)
        if view == "full":
            data = raw_issue
        else:
            base_url = view_base_url(config)
            data = presenter.compact_issue(raw_issue, view=view, base_url=base_url)
        return _build_result(data, "get_issue", started=started)
    except Exception as e:
        return _error_result("get_issue", e, started=started)


@mcp.tool()
def get_issues(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    query: Annotated[str, Field(description="Search keyword for issue summary or description. Omit or pass an empty string for no keyword filter.")] = "",
    issue_types: Annotated[tuple[str, ...], Field(description="Issue type names to include, e.g. ('Bug', 'Story'). Omit for all issue types.")] = (),
    include_closed: Annotated[bool, Field(description="Set true to include Closed issues; false returns open issues only.")] = False,
    limit: Annotated[int, Field(description="Maximum issues to return, from 1 to 100.", ge=1, le=100)] = 50,
    cursor: Annotated[str, Field(description="Offset cursor for pagination (e.g., '50' to start from the 50th item). Omit or pass an empty string to start from the beginning.")] = "",
    sort: Annotated[
        IssueSort | None,
        Field(
            description="Backlog issue sort field, e.g. updated, dueDate, priority. Omit for Backlog default ordering."
        ),
    ] = None,
    order: Annotated[
        SortOrder | None,
        Field(
            description="Sort order: asc or desc. Omit for Backlog default ordering."
        ),
    ] = None,
) -> CallToolResult:
    """List issues assigned to the configured user in one project.

    Use when you need a paginated, filterable issue search across types.
    Do not use when the user asks specifically for open personal bugs; use get_my_open_bugs.
    """
    started = time.monotonic()
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_issues", e, started=started, project=project_key)

    try:
        config = get_config_instance()
        me = config.get("defaults", {}).get("assignee", "me")
        assignee_id = resolve_user_id(config, me)
        raw_issues = issue_service.get_issues(
            config,
            project_key=project_key or None,
            query=query or None,
            assignee_id=assignee_id,
            open_only=not include_closed,
            issue_types=list(issue_types) if issue_types else None,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            start_path=_workspace_path(),
        )
        base_url = view_base_url(config)
        data = [presenter.compact_issue(item, view="compact", base_url=base_url) for item in raw_issues]
        return _build_result(
            data,
            "get_issues",
            list_key="issues",
            limit=limit,
            offset=offset,
            paginated=True,
            started=started,
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_issues", e, started=started, project=project_key)


@mcp.tool()
def create_issue(
    summary: Annotated[str, Field(description="Issue summary title")],
    issue_type: Annotated[str, Field(description="Issue type name or ID (e.g., 'Bug', 'Task', 'Story'). Required by Backlog for creation.")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    parent_key: Annotated[str, Field(description="Parent issue key (e.g., 'PRJ-123'). Omit or pass an empty string for no parent.")] = "",
    description: Annotated[str, Field(description="Issue description detail text. Omit or pass an empty string for no description.")] = "",
    priority: Annotated[str, Field(description="Priority name or ID (e.g., 'High', 'Normal', 'Low'). Omit for project default.")] = "",
    assignee: Annotated[str, Field(description="Assignee user reference from config.users or raw user ID. Omit for project default.")] = "",
    category: Annotated[str, Field(description="Category name or ID. Omit for no category.")] = "",
    start_date: Annotated[str, Field(description="Start date in YYYY-MM-DD format. Omit for no start date.")] = "",
    due_date: Annotated[str, Field(description="Due date in YYYY-MM-DD format. Omit for no due date.")] = "",
    estimated_hours: Annotated[float | None, Field(description="Estimated hours. Omit when unknown.")] = None,
    actual_hours: Annotated[float | None, Field(description="Actual hours. Omit when unknown.")] = None,
    custom_fields: Annotated[dict[str, Any] | None, Field(description="Custom field values keyed by configured custom field key, e.g. {'qc_activity':'Unit Test'}.")] = None,
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned change without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Create a Backlog issue.

    Use when the user asks to create a generic Backlog issue and has supplied the issue type.
    Do not use when the user asks for the opinionated Unit Test bug workflow; use create_ut_bug.
    """
    started = time.monotonic()
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        res = issue_service.create_issue(
            config,
            summary=summary,
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
            dry_run=dry_run,
            workspace_path=_workspace_path(),
        )
        if dry_run:
            data = res
        else:
            base_url = view_base_url(config)
            data = presenter.compact_issue(res, view="compact", base_url=base_url)
        return _build_result(
            data,
            "create_issue",
            started=started,
            dry_run=dry_run,
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_issue", e, started=started, dry_run=dry_run, project=project_key)


@mcp.tool()
def update_issue(
    issue_id: Annotated[str, Field(description="Issue key (e.g., 'PROJ-123') or numeric ID")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to infer from issue key or active workspace context.")] = "",
    summary: Annotated[str, Field(description="New issue summary title. Omit or pass an empty string to keep current summary.")] = "",
    status: Annotated[str, Field(description="Status name or ID to transition to. Omit to keep current status.")] = "",
    comment: Annotated[str, Field(description="Comment text to add to the update. Omit for no comment.")] = "",
    description: Annotated[str, Field(description="New description detail text. Omit to keep current description.")] = "",
    priority: Annotated[str, Field(description="New priority name or ID. Omit to keep current priority.")] = "",
    assignee: Annotated[str, Field(description="New assignee user reference or raw user ID. Omit to keep current assignee.")] = "",
    category: Annotated[str, Field(description="New category name or ID. Omit to keep current categories.")] = "",
    start_date: Annotated[str, Field(description="New start date in YYYY-MM-DD format. Omit to keep current start date.")] = "",
    due_date: Annotated[str, Field(description="New due date in YYYY-MM-DD format. Omit to keep current due date.")] = "",
    estimated_hours: Annotated[float | None, Field(description="New estimated hours. Omit to keep current value.")] = None,
    actual_hours: Annotated[float | None, Field(description="New actual hours. Omit to keep current value.")] = None,
    custom_fields: Annotated[dict[str, Any] | None, Field(description="Custom field updates keyed by configured custom field key.")] = None,
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned change without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Update a Backlog issue.

    Use when the user asks to change fields on an existing issue.
    Do not use when the user asks to complete the bug resolution workflow; use resolve_bug.
    """
    started = time.monotonic()
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        res = issue_service.update_issue(
            config,
            issue_id=issue_id,
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
            dry_run=dry_run,
            workspace_path=_workspace_path(),
        )
        if dry_run:
            data = res
        else:
            base_url = view_base_url(config)
            data = presenter.compact_issue(res, view="compact", base_url=base_url)
        return _build_result(
            data,
            "update_issue",
            started=started,
            dry_run=dry_run,
            project=project_key,
        )
    except Exception as e:
        return _error_result("update_issue", e, started=started, dry_run=dry_run, project=project_key)


@mcp.tool()
def get_my_open_bugs(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    query: Annotated[str, Field(description="Search keyword for bug summary or description. Omit or pass an empty string for no keyword filter.")] = "",
    limit: Annotated[int, Field(description="Maximum bugs to return, from 1 to 100.", ge=1, le=100)] = 50,
    cursor: Annotated[str, Field(description="Offset cursor for pagination (e.g., '50' to start from the 50th item). Omit or pass an empty string to start from the beginning.")] = "",
    sort: Annotated[
        IssueSort | None,
        Field(
            description="Backlog issue sort field, e.g. updated, dueDate, priority. Omit for Backlog default ordering."
        ),
    ] = None,
    order: Annotated[
        SortOrder | None,
        Field(
            description="Sort order: asc or desc. Omit for Backlog default ordering."
        ),
    ] = None,
) -> CallToolResult:
    """List open bugs assigned to the configured user in one project.

    Use when the user asks for their current open bugs or bug triage queue.
    Do not use for generic issue search across issue types; use get_issues.
    """
    started = time.monotonic()
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_my_open_bugs", e, started=started, project=project_key)

    try:
        config = get_config_instance()
        bugs = bug_workflow.my_open_bugs_raw(
            config,
            project_key=project_key or None,
            query=query or None,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            start_path=_workspace_path(),
        )
        base_url = view_base_url(config)
        data = [presenter.compact_issue(item, view="compact", base_url=base_url) for item in bugs]
        return _build_result(
            data,
            "get_my_open_bugs",
            list_key="bugs",
            limit=limit,
            offset=offset,
            paginated=True,
            started=started,
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_my_open_bugs", e, started=started, project=project_key)


@mcp.tool()
def get_bug_context(
    issue_key: Annotated[str, Field(description="Bug issue key (e.g., 'PRJ-123') to analyze")],
) -> CallToolResult:
    """Get AI-ready context for a specific bug, including fields needed to understand, discuss, or resolve it.

    Use when preparing to understand, fix, discuss, or resolve a specific bug.
    Do not use for listing bugs; use get_my_open_bugs.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        data = bug_workflow.get_bug_context(config, issue_key)
        return _build_result(data, "get_bug_context", started=started)
    except Exception as e:
        return _error_result("get_bug_context", e, started=started)


@mcp.tool()
def resolve_bug(
    issue_key: Annotated[str, Field(description="Bug issue key to resolve (e.g., 'PRJ-123')")],
    status: Annotated[str, Field(description="Target status name or ID. Omit to use the configured resolved/closed status.")] = "",
    actual_hours: Annotated[float | None, Field(description="Actual hours spent fixing the bug. Omit when unknown.")] = None,
    estimated_hours: Annotated[float | None, Field(description="Estimated hours. Omit when unknown.")] = None,
    qc_activity: Annotated[str, Field(description="Quality control activity name where bug was found, e.g. 'Unit Test'.")] = "",
    cause_category: Annotated[str, Field(description="Cause category name, e.g. 'COD_Coding Logic'.")] = "",
    bug_origin: Annotated[str, Field(description="Bug origin category name.")] = "",
    impacted: Annotated[str, Field(description="Impacted component, module, screen, or feature area.")] = "",
    resolution: Annotated[str, Field(description="Resolution category or summary required by the bug workflow.")] = "",
    comment: Annotated[str, Field(description="Resolve comment text.")] = "",
    commit: Annotated[str, Field(description="Git commit hash/ref related to the fix.")] = "",
    fix_description: Annotated[str, Field(description="Corrective action or fix description text.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned resolution without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Resolve a bug with workflow defaults.

    Use when the user asks to resolve/close a bug and wants project workflow fields filled.
    Do not use for generic issue updates unrelated to bug resolution; use update_issue.
    """
    started = time.monotonic()
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        res = bug_workflow.resolve_bug(
            config,
            issue_key=issue_key,
            dry_run=dry_run,
            status=status,
            actual_hours=actual_hours,
            estimated_hours=estimated_hours,
            qc_activity=qc_activity,
            cause_category=cause_category,
            bug_origin=bug_origin,
            impacted=impacted,
            resolution=resolution,
            comment=comment,
            commit=commit,
            fix_description=fix_description,
            start_path=_workspace_path(),
        )
        if dry_run:
            data = {
                "dryRun": True,
                "issue": res.get("issue"),
                "project": res.get("project"),
                "assignment": res.get("assignment"),
                "changes": res.get("changes", []),
                "warnings": res.get("warnings", []),
            }
        else:
            base_url = view_base_url(config)
            data = presenter.compact_issue(res, view="compact", base_url=base_url)
        return _build_result(
            data,
            "resolve_bug",
            started=started,
            dry_run=dry_run,
        )
    except Exception as e:
        return _error_result("resolve_bug", e, started=started, dry_run=dry_run)


@mcp.tool()
def create_ut_bug(
    parent_key: Annotated[str, Field(description="Parent issue key (e.g., 'PRJ-123') to attach the UT bug to")],
    module: Annotated[str, Field(description="Name of the module or file with the failing unit test")],
    description: Annotated[str, Field(description="Unit test failure description details")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned bug without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Create a Unit Test sub-task bug under a parent issue.

    Use when the user asks to create a UT bug with the configured workflow defaults.
    Do not use for generic bugs or tasks; use create_issue.
    """
    started = time.monotonic()
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        res = ut_bug.create_subtask_bug(
            config,
            project_key=project_key or None,
            parent_key=parent_key,
            module=module,
            description=description,
            dry_run=dry_run,
            start_path=_workspace_path(),
        )
        if dry_run:
            data = res
        else:
            data = {"issueKey": res.get("issueKey"), "applied": True}
        return _build_result(
            data,
            "create_ut_bug",
            started=started,
            dry_run=dry_run,
            project=project_key,
        )
    except ut_bug.PostCreateUpdateError as e:
        return _partial_write_result(
            "create_ut_bug",
            str(e),
            {
                "issueKey": e.issue_key,
                "committed": {"created": True, "postCreateUpdate": False},
                "retrySafe": False,
                "recovery": {
                    "action": "update_existing_issue",
                    "issueKey": e.issue_key,
                    "targetStatus": e.target_status,
                    "updatePayload": e.payload,
                },
            },
            started=started,
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_ut_bug", e, started=started, dry_run=dry_run, project=project_key)


@mcp.tool()
def get_bug_rules(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
) -> CallToolResult:
    """Get current resolve-bug workflow rules for one project.

    Use when preparing a bug resolution and you need required workflow defaults.
    Do not use for issue data; use get_bug_context or get_issue.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        data = guidance.resolve_rules(config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_rules", started=started, project=project_key)
    except Exception as e:
        return _error_result("get_bug_rules", e, started=started, project=project_key)


@mcp.tool()
def get_bug_fields(
    field: Annotated[str, Field(description="Field name to get guidance for, e.g. qc_activity, bug_origin, cause_category. Omit for all fields.")] = "",
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
) -> CallToolResult:
    """Get configured guidance for bug workflow fields.

    Use when you need allowed values or guidance for resolve_bug fields.
    Do not use to update an issue; use resolve_bug or update_issue.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        data = guidance.field_guidance(field or None, config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_fields", started=started, project=project_key)
    except Exception as e:
        return _error_result("get_bug_fields", e, started=started, project=project_key)


@mcp.tool()
def get_my_work_overview(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    query: Annotated[str, Field(description="Search keyword for story/task summary or description. Omit or pass an empty string for no keyword filter.")] = "",
    limit: Annotated[int, Field(description="Maximum stories/tasks to return, from 1 to 100.", ge=1, le=100)] = 50,
    cursor: Annotated[str, Field(description="Offset cursor for pagination (e.g., '50' to start from the 50th item). Omit or pass an empty string to start from the beginning.")] = "",
    sort: Annotated[
        IssueSort | None,
        Field(
            description="Backlog issue sort field, e.g. updated, dueDate, priority. Omit for Backlog default ordering."
        ),
    ] = None,
    order: Annotated[
        SortOrder | None,
        Field(
            description="Sort order: asc or desc. Omit for Backlog default ordering."
        ),
    ] = None,
) -> CallToolResult:
    """Get assigned Story and Task work items with deadline and status context.

    Use when the user asks for assigned stories/tasks, due dates, or project status.
    Do not use for generic issue search or bug triage; use get_issues or get_my_open_bugs.
    """
    started = time.monotonic()
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_my_work_overview", e, started=started, project=project_key)

    try:
        config = get_config_instance()
        stories = story_task_overview.my_story_task_overview(
            config,
            project_key=project_key or None,
            query=query or None,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            start_path=_workspace_path(),
        )
        return _build_result(
            stories,
            "get_my_work_overview",
            list_key="stories",
            limit=limit,
            offset=offset,
            paginated=True,
            started=started,
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_my_work_overview", e, started=started, project=project_key)


@mcp.tool()
def list_configured_projects() -> CallToolResult:
    """List configured Backlog projects without querying every project.

    Use when choosing or confirming a project key.
    Do not use to fetch live project metadata; use inspect_project for one explicit project.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        rows = []
        for key in project_keys(config):
            try:
                catalog = load_project_catalog(key)
                rows.append({"key": key, "id": catalog.get("id"), "name": catalog.get("name")})
            except Exception:
                rows.append({"key": key, "id": None, "name": "(missing catalog)"})
        return _build_result(rows, "list_configured_projects", list_key="projects", started=started)
    except Exception as e:
        return _error_result("list_configured_projects", e, started=started)


@mcp.tool()
def get_config() -> CallToolResult:
    """Get local Backlog configuration settings with credentials excluded.

    Use when diagnosing local MCP configuration or defaults.
    Do not use to retrieve secrets; credentials are intentionally excluded.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        return _build_result(redact_config(config), "get_config", started=started)
    except Exception as e:
        return _error_result("get_config", e, started=started)


@mcp.tool()
def audit_config_workflows(
    mode: Annotated[
        Literal["local", "live"],
        Field(
            description="local validates workflow/config compatibility against cached catalogs; live compares cached catalogs with current Backlog metadata without writing files."
        ),
    ] = "local",
) -> CallToolResult:
    """Validate workflow config and optionally detect live Backlog catalog drift.

    Use local mode for config/workflow consistency. Use live mode before relying on
    catalog-backed mutations when Backlog metadata may have changed.
    Do not use to refresh catalogs; live mode is read-only.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        data = audit_config(config, mode=mode)
        return _build_result(data, "audit_config_workflows", started=started)
    except Exception as e:
        return _error_result("audit_config_workflows", e, started=started)


@mcp.tool()
def inspect_project(
    project_key: Annotated[str, Field(description="Project key to inspect (e.g., 'PRJ')")],
    mode: Annotated[Literal["read", "refresh_catalog"], Field(description="read fetches metadata without writing; refresh_catalog writes the local project catalog.")] = "read",
) -> CallToolResult:
    """Fetch project metadata or refresh one local project catalog.

    Use when the user names one project and needs its metadata or catalog refreshed.
    Do not use to enumerate every project; use list_configured_projects.
    """
    started = time.monotonic()
    try:
        config = get_config_instance()
        project_config = build_project_config(config, project_key)
        if mode == "read":
            data = project_config
        else:
            path = write_catalog(project_config)
            data = {"wrote": path, "key": project_config["key"]}
        return _build_result(
            data,
            "inspect_project",
            started=started,
            project=project_key,
        )
    except Exception as e:
        return _error_result("inspect_project", e, started=started, project=project_key)


@mcp.prompt()
def resolve_bug_prompt(
    issue_key: Annotated[str, Field(description="The key of the bug issue to resolve (e.g., 'PRJ-123')")]
) -> str:
    """Guide the agent to resolve a bug following project workflow policies."""
    return (
        f"Please guide me to resolve the bug {issue_key} following our project's workflow rules.\n\n"
        f"Steps to take:\n"
        f"1. Fetch the bug context using `get_bug_context` for {issue_key}.\n"
        f"2. Fetch the resolve-bug rules using `get_bug_rules` for the project.\n"
        f"3. Retrieve guidelines for any required guided fields using `get_bug_fields`.\n"
        f"4. Summarize the required values and ask for confirmation if any value is inferred or missing.\n"
        f"5. Execute `resolve_bug` only after the user explicitly confirms the final values or has clearly requested resolution."
    )


@mcp.prompt()
def create_ut_bug_prompt(
    parent_key: Annotated[str, Field(description="The parent issue key (e.g., 'PRJ-123')")],
    module: Annotated[str, Field(description="The name of the module or component under test")],
    description: Annotated[str, Field(description="Optional failure description or detail text for the UT bug")] = "",
) -> str:
    """Guide the agent to create a Unit Test sub-task bug under a parent issue."""
    desc_val = f"'{description}'" if description else "(not specified yet)"
    return (
        f"I need to create a Unit Test (UT) child bug for the parent issue {parent_key} and module {module}.\n"
        f"Current failure description: {desc_val}\n\n"
        f"Steps to take:\n"
        f"1. Inspect the parent issue context using `get_issue` for {parent_key}.\n"
        f"2. If the failure description is empty, inspect the parent issue and ask for or draft a concise UT failure description before calling `create_ut_bug`.\n"
        f"3. Once parent, module, and description are confirmed, execute `create_ut_bug` to create the task on Backlog."
    )


@mcp.prompt()
def project_status_prompt(
    project: Annotated[str, Field(description="Project key. Omit only when the active workspace can resolve the project unambiguously; otherwise the tool should return an error.")] = ""
) -> str:
    """Guide the agent to check the current project status overview."""
    proj_desc = f"project '{project}'" if project else "the active workspace"
    return (
        f"Please check and summarize the current status of {proj_desc}.\n\n"
        f"Steps to take:\n"
        f"0. If the project is omitted and cannot be resolved unambiguously, stop and report the ambiguity instead of guessing.\n"
        f"1. Retrieve story and task deadlines using `get_my_work_overview`.\n"
        f"2. List open bugs assigned to me using `get_my_open_bugs`.\n"
        f"3. Present a clear, consolidated status report highlighting any overdue deadlines or critical bugs."
    )


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return config
    redacted = {}
    sensitive_substrings = {
        "token", "secret", "password", "api_key", "apikey", "api-key",
        "private_key", "authorization", "cookie", "passwd"
    }
    for k, v in config.items():
        k_lower = k.lower()
        is_sensitive = (
            any(sub in k_lower for sub in sensitive_substrings)
            or k_lower == "auth"
            or k_lower.startswith("auth_")
        )
        if is_sensitive:
            continue
        if isinstance(v, dict):
            redacted[k] = redact_config(v)
        elif isinstance(v, list):
            redacted[k] = [redact_config(item) if isinstance(item, dict) else item for item in v]
        else:
            redacted[k] = v
    return redacted


@mcp.resource(
    "backlog://config",
    mime_type="application/json",
    meta={"kind": "config", "scope": "workstation"},
)
def config_resource() -> str:
    """Read the workstation-wide Backlog configuration as JSON."""
    return json.dumps(redact_config(load_config()), indent=2, ensure_ascii=False)


@mcp.resource(
    "backlog://metrics",
    mime_type="application/json",
    meta={"kind": "metrics", "scope": "workstation"},
)
def metrics_resource() -> str:
    """Read aggregated local MCP usage metrics as JSON."""
    return json.dumps(summarize_metrics(), indent=2, ensure_ascii=False)


@mcp.resource(
    "backlog://issue/{issue_key}",
    mime_type="application/json",
    meta={"kind": "issue", "scope": "project"},
)
def issue_resource(issue_key: str) -> str:
    """Read one Backlog issue as JSON by issue key."""
    try:
        config = get_config_instance()
        data = issue_service.get_issue(config, issue_key)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, indent=2, ensure_ascii=False)


def main() -> None:
    """Run the workstation-local server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
