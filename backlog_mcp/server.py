#!/usr/bin/env python3
"""Stdio MCP server exposing the Backlog integration to every local project."""

import json
import os
from typing import Annotated, Any, Literal, Sequence

from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from backlog_tool.cli import execute
from backlog_tool.settings import load_config, summarize_metrics


class IssueCompact(BaseModel):
    issueKey: str
    summary: str
    description: str | None = None
    issueType: str | None = None
    status: str | None = None
    assignee: str | None = None
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    estimatedHours: float | None = None
    actualHours: float | None = None
    resourceUri: str | None = None
    url: str | None = None
    daysUntilDue: int | None = None
    dueAlertLevel: int | None = None
    customFields: list[dict[str, Any]] | None = None


class PaginationInfo(BaseModel):
    limit: int
    nextCursor: str | None = None
    hasMore: bool


class GetIssuesData(BaseModel):
    issues: list[IssueCompact]


class GetIssuesResponse(BaseModel):
    ok: bool
    data: GetIssuesData
    pagination: PaginationInfo


class GetBugsData(BaseModel):
    bugs: list[IssueCompact]


class GetBugsResponse(BaseModel):
    ok: bool
    data: GetBugsData
    pagination: PaginationInfo


class GetIssueResponse(BaseModel):
    ok: bool
    data: IssueCompact


class GetStoriesData(BaseModel):
    stories: list[IssueCompact]


class GetStoriesResponse(BaseModel):
    ok: bool
    data: GetStoriesData
    pagination: PaginationInfo


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


def _append(args: list[str], flag: str, value: Any) -> None:
    if value not in (None, ""):
        args.extend((flag, str(value)))


def _append_many(args: list[str], flag: str, values: Sequence[str] | None) -> None:
    for value in values or []:
        if value:
            args.extend((flag, value))


def _append_custom_fields(args: list[str], custom_fields: dict[str, Any] | None) -> None:
    for key, value in (custom_fields or {}).items():
        if value not in (None, ""):
            args.extend(("--custom", f"{key}={value}"))


def _append_apply_mode(args: list[str], mode: MutationMode) -> None:
    if mode == "apply":
        args.extend(("--apply",))


def _append_list_controls(
    args: list[str],
    *,
    limit: int,
    offset: int,
    sort: str | None,
    order: str | None,
) -> None:
    args.extend(("--limit", str(limit), "--offset", str(offset)))
    _append(args, "--sort", sort)
    _append(args, "--order", order)


def _build_issue_list_args(
    *,
    command: list[str],
    project: str,
    query: str,
    limit: int,
    offset: int,
    sort: IssueSort | None,
    order: SortOrder | None,
) -> list[str]:
    args = command.copy()

    _append_list_controls(
        args,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )

    _append(args, "--project", project)
    _append(args, "--query", query)

    return args


def _to_markdown(data: Any, args: Sequence[str]) -> str:
    if not data:
        return "No data."
    command_name = ":".join(args[:2]) if len(args) >= 2 else ":".join(args)
    if isinstance(data, list):
        count = len(data)
        summary = f"Retrieved {count} items via '{command_name}'."
        if count > 0:
            lines = [summary, ""]
            for item in data:
                if isinstance(item, dict):
                    key = item.get("issueKey") or item.get("key") or ""
                    title = item.get("summary") or ""
                    status = item.get("status") or ""
                    status_suffix = f" [{status}]" if status else ""
                    lines.append(f"- **{key}**: {title}{status_suffix}")
            lines.append("\nFull details are available in the structured content.")
            return "\n".join(lines)
        return summary
    elif isinstance(data, dict):
        key = data.get("issueKey") or data.get("key")
        title = data.get("summary")
        status = data.get("status")
        if key and title:
            status_suffix = f" [{status}]" if status else ""
            return f"Retrieved item **{key}**: {title}{status_suffix}.\nFull details are available in the structured content."
        lines = [f"Result of '{command_name}':", ""]
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append(f"- **{k}**: (structured data)")
            else:
                lines.append(f"- **{k}**: {v}")
        return "\n".join(lines)
    return str(data)


def _item_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if data in (None, "", [], {}):
        return 0
    return 1


def _pagination(limit: int, offset: int, returned: int, enabled: bool) -> dict[str, Any]:
    has_more = bool(enabled and limit > 0 and returned >= limit)
    next_cursor = str(offset + returned) if has_more else None
    return {
        "limit": limit if enabled else 0,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


def _parse_cursor(cursor: str) -> int:
    if not cursor:
        return 0
    try:
        offset = int(cursor)
        if offset < 0:
            raise ValueError("Cursor (offset) must be a non-negative integer.")
        return offset
    except ValueError:
        raise ValueError(f"Invalid cursor format: '{cursor}'. Cursor must be a non-negative integer string representing the offset (e.g., '50').")


def _normalize_data(data: Any, args: list[str]) -> Any:
    if not data:
        return data
    group = args[0] if len(args) > 0 else ""
    action = args[1] if len(args) > 1 else ""
    
    if group in ("issue", "bug", "story"):
        # Skip bug sub-commands that return rule configs or context
        if group == "bug" and action in ("context", "rules", "fields"):
            return data
            
        if isinstance(data, list):
            normalized = []
            for item in data:
                if isinstance(item, dict):
                    try:
                        normalized.append(IssueCompact.model_validate(item).model_dump(exclude_none=True))
                    except Exception:
                        normalized.append(item)
                else:
                    normalized.append(item)
            return normalized
        elif isinstance(data, dict):
            try:
                return IssueCompact.model_validate(data).model_dump(exclude_none=True)
            except Exception:
                return data
    return data


def _resource_uris(data: Any) -> list[str]:
    items = data if isinstance(data, list) else [data]
    uris = []
    for item in items:
        if isinstance(item, dict):
            issue_key = item.get("issueKey") or item.get("issue")
            if issue_key:
                uris.append(f"backlog://issue/{issue_key}")
    return sorted(set(uris))


def _envelope(
    *,
    ok: bool,
    data: Any,
    list_key: str | None,
    limit: int,
    offset: int,
    paginated: bool,
) -> dict[str, Any]:
    result_data = {list_key or "items": data} if isinstance(data, list) else data
    returned = _item_count(data)
    
    envelope_data = {
        "ok": ok,
        "data": result_data if result_data is not None else {},
    }
    if paginated:
        envelope_data["pagination"] = _pagination(limit, offset, returned, paginated)
    return envelope_data


def _error_result(args: Sequence[str], error: Exception) -> CallToolResult:
    message = str(error)
    return CallToolResult(
        content=[TextContent(type="text", text=f"Error: {message}")],
        structuredContent=None,
        isError=True,
    )


def _workspace_path() -> str | None:
    """Resolve the active client workspace without exposing it as a tool input."""
    return (
        os.environ.get("BACKLOG_WORKSPACE_PATH")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or None
    )


def _invoke(
    args: list[str],
    list_key: str | None = None,
    full: bool = False,
    limit: int = 0,
    offset: int = 0,
    paginated: bool = False,
) -> CallToolResult:
    if full:
        if "--json-full" not in args:
            args.append("--json-full")
    try:
        res = execute(args, workspace_path=_workspace_path())
    except Exception as error:
        return _error_result(args, error)
    data = res.data
    
    if not full:
        data = _normalize_data(data, args)
        
    text = _to_markdown(data, args)

    structured = _envelope(
        ok=True,
        data=data,
        list_key=list_key,
        limit=limit,
        offset=offset,
        paginated=paginated,
    )
    
    uris = _resource_uris(data)

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        _meta={
            "command": ":".join(args[:2]) if len(args) >= 2 else ":".join(args),
            "resourceUris": uris,
        }
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
    full = (view == "full")
    return _invoke(["issue", "get", issue_id], full=full)


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
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result(["issue", "list"], e)

    args = _build_issue_list_args(
        command=["issue", "list"],
        project=project_key,
        query=query,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    _append_many(args, "--type", issue_types)
    _append(args, "--view", "compact")
    if include_closed:
        args.append("--all")
    return _invoke(args, list_key="issues", full=False, limit=limit, offset=offset, paginated=True)


def _append_issue_fields(
    args: list[str],
    *,
    description: str | None,
    priority: str | None,
    assignee: str | None,
    category: str | None,
    start_date: str | None,
    due_date: str | None,
    estimated_hours: float | None,
    actual_hours: float | None,
    custom_fields: dict[str, Any] | None,
) -> None:
    _append(args, "--desc", description)
    _append(args, "--priority", priority)
    _append(args, "--assignee", assignee)
    _append(args, "--category", category)
    _append(args, "--start-date", start_date)
    _append(args, "--due-date", due_date)
    _append(args, "--estimated-hours", estimated_hours)
    _append(args, "--actual-hours", actual_hours)
    _append_custom_fields(args, custom_fields)


def _build_issue_update_args(
    command: list[str],
    issue_id: str,
    *,
    project: str = "",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    category: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours: float | None = None,
    actual_hours: float | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> list[str]:
    args = command + [issue_id]

    _append(args, "--project", project)

    _append_issue_fields(
        args,
        description=description,
        priority=priority,
        assignee=assignee,
        category=category,
        start_date=start_date,
        due_date=due_date,
        estimated_hours=estimated_hours,
        actual_hours=actual_hours,
        custom_fields=custom_fields,
    )

    return args


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
    args = ["issue", "create", summary]
    _append(args, "--project", project_key)
    _append(args, "--issue-type", issue_type)
    _append(args, "--parent", parent_key)
    _append_issue_fields(
        args,
        description=description,
        priority=priority,
        assignee=assignee,
        category=category,
        start_date=start_date,
        due_date=due_date,
        estimated_hours=estimated_hours,
        actual_hours=actual_hours,
        custom_fields=custom_fields,
    )
    _append_apply_mode(args, mode)
    return _invoke(args)


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
    args = _build_issue_update_args(
        ["issue", "update"],
        issue_id,
        project=project_key,
        description=description,
        priority=priority,
        assignee=assignee,
        category=category,
        start_date=start_date,
        due_date=due_date,
        estimated_hours=estimated_hours,
        actual_hours=actual_hours,
        custom_fields=custom_fields,
    )
    _append(args, "--summary", summary)
    _append(args, "--status", status)
    _append(args, "--comment", comment)
    _append_apply_mode(args, mode)
    return _invoke(args)


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
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result(["bug", "list"], e)

    args = _build_issue_list_args(
        command=["bug", "list"],
        project=project_key,
        query=query,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    return _invoke(args, list_key="bugs", full=False, limit=limit, offset=offset, paginated=True)


@mcp.tool()
def get_bug_context(
    issue_key: Annotated[str, Field(description="Bug issue key (e.g., 'PRJ-123') to analyze")],
) -> CallToolResult:
    """Get AI-ready context for a specific bug, including fields needed to understand, discuss, or resolve it.

    Use when preparing to understand, fix, discuss, or resolve a specific bug.
    Do not use for listing bugs; use get_my_open_bugs.
    """
    return _invoke(["bug", "context", issue_key])


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
    args = ["bug", "resolve", issue_key]
    for flag, value in (
        ("--status", status),
        ("--actual-hours", actual_hours),
        ("--estimated-hours", estimated_hours),
        ("--qc-activity", qc_activity),
        ("--cause-category", cause_category),
        ("--bug-origin", bug_origin),
        ("--impacted", impacted),
        ("--resolution", resolution),
        ("--comment", comment),
        ("--commit", commit),
        ("--fix-description", fix_description),
    ):
        _append(args, flag, value)
    _append_apply_mode(args, mode)
    return _invoke(args)


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
    args = ["bug", "create-ut", parent_key, module, description]
    _append(args, "--project", project_key)
    _append_apply_mode(args, mode)
    return _invoke(args)


@mcp.tool()
def get_bug_rules(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
) -> CallToolResult:
    """Get current resolve-bug workflow rules for one project.

    Use when preparing a bug resolution and you need required workflow defaults.
    Do not use for issue data; use get_bug_context or get_issue.
    """
    args = ["bug", "rules"]
    _append(args, "--project", project_key)
    return _invoke(args)


@mcp.tool()
def get_bug_fields(
    field: Annotated[str, Field(description="Field name to get guidance for, e.g. qc_activity, bug_origin, cause_category. Omit for all fields.")] = "",
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
) -> CallToolResult:
    """Get configured guidance for bug workflow fields.

    Use when you need allowed values or guidance for resolve_bug fields.
    Do not use to update an issue; use resolve_bug or update_issue.
    """
    args = ["bug", "fields"]
    if field:
        args.append(field)
    _append(args, "--project", project_key)
    return _invoke(args)


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
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result(["story", "overview"], e)

    args = _build_issue_list_args(
        command=["story", "overview"],
        project=project_key,
        query=query,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    return _invoke(args, list_key="stories", limit=limit, offset=offset, paginated=True)


@mcp.tool()
def list_configured_projects() -> CallToolResult:
    """List configured Backlog projects without querying every project.

    Use when choosing or confirming a project key.
    Do not use to fetch live project metadata; use inspect_project for one explicit project.
    """
    return _invoke(["config", "list-projects"], list_key="projects")


@mcp.tool()
def get_config() -> CallToolResult:
    """Get local Backlog configuration settings with credentials excluded.

    Use when diagnosing local MCP configuration or defaults.
    Do not use to retrieve secrets; credentials are intentionally excluded.
    """
    return _invoke(["config", "show"])


@mcp.tool()
def audit_config_workflows() -> CallToolResult:
    """Validate workflow config, policies, and project catalogs for drift.

    Use when configuration behavior looks wrong or before relying on workflow defaults.
    Do not use for issue search or project status summaries.
    """
    return _invoke(["config", "audit-workflows"])


@mcp.tool()
def inspect_project(
    project_key: Annotated[str, Field(description="Project key to inspect (e.g., 'PRJ')")],
    mode: Annotated[Literal["read", "refresh_catalog"], Field(description="read fetches metadata without writing; refresh_catalog writes the local project catalog.")] = "read",
) -> CallToolResult:
    """Fetch project metadata or refresh one local project catalog.

    Use when the user names one project and needs its metadata or catalog refreshed.
    Do not use to enumerate every project; use list_configured_projects.
    """
    args = ["project", "inspect", project_key]
    if mode == "read":
        args.append("--stdout")
    return _invoke(args)


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
    result = _invoke(["issue", "get", issue_key], full=True)
    if result.isError or result.structuredContent is None:
        err_msg = result.content[0].text if (result.content and len(result.content) > 0) else "Unknown error"
        if err_msg.startswith("Error: "):
            err_msg = err_msg[7:]
        return json.dumps({"ok": False, "error": err_msg}, indent=2, ensure_ascii=False)
    return json.dumps(result.structuredContent, indent=2, ensure_ascii=False)


def main() -> None:
    """Run the workstation-local server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
