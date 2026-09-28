#!/usr/bin/env python3
"""Stdio MCP server exposing the Backlog integration to every local project."""

import json
import os
import re
from typing import Annotated, Any, Literal

import anyio
from pydantic import ConfigDict, Field, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase
from mcp.types import CallToolResult, ToolAnnotations

from .arg_errors import describe_validation_error, format_arg_error
from .results import _build_result, _error_result, _parse_cursor, _partial_write_result

from backlog_tool.settings import (
    load_config,
    load_env_file,
    project_keys,
    project_key_from_issue_id,
    view_base_url,
    find_eval_marker,
)
from backlog_tool import issue_service, presenter
from workflows import guidance, ut_bug
from workflows.bug_template import issue_context
import workflows.resolve_bug as bug_workflow
from backlog_tool.telemetry import (
    log_session_start,
    record_arg_error,
    reset_client_arguments,
    set_client_arguments,
    start_call,
)

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

def _forbid_unknown_tool_arguments() -> None:
    """Reject tool arguments that are not declared in the generated MCP schema.

    mcp<2 currently inherits Pydantic's extra="ignore" behavior for generated
    FastMCP argument models, which can silently discard misspelled or
    hallucinated fields. Configure the shared argument base before any tools are
    registered so generated schemas also advertise additionalProperties=false.
    """
    ArgModelBase.model_config = ConfigDict(
        **dict(ArgModelBase.model_config),
        extra="forbid",
    )


_forbid_unknown_tool_arguments()


SERVER_INSTRUCTIONS = """Personal Backlog MCP: every tool acts as the owner of the API key (a developer, not a PM).

Activation:
- Use these tools only when the user mentions Backlog, gives a Backlog issue key (e.g. OOP-123) or a Backlog URL.
- Do not route generic requests such as "what should I do?" or "project status" here without that signal.

Intent -> tool:
- My open bugs -> list_my_issues(issue_types=["Bug"])
- My stories/tasks or deadlines -> list_my_issues(issue_types=["Story", "Task"])
- What do I have to do / my Backlog status -> list_my_issues()
- Investigate or fix a bug that is not fixed yet -> get_issue
- Resolve/close a bug, or the user says it is fixed -> resolve_bug(mode="apply"), one call, no lookups first
- Unit Test bug found while working on an issue -> create_ut_bug
- Other issue changes the user asks for: create_issue, update_issue

Behavior:
- Writes (resolve_bug, create_issue, update_issue, create_ut_bug): call with mode="apply" directly; use mode="preview" only when the user asks to preview. Afterwards report the returned changes and every warning.
- get_issue lists attachments but not their content; tell the user when one matters.

Project:
- An issue key's prefix is its project (OOP-123 -> OOP).
- Without a key, the server resolves the project from the workspace. If it reports it cannot, use a project the user or conversation named; otherwise ask the user. Never guess.
"""

mcp = FastMCP(
    name="Backlog Local",
    instructions=SERVER_INSTRUCTIONS,
    json_response=True,
)


def _record_rejected_tool_calls() -> None:
    """Log calls FastMCP rejects before the tool body runs.

    Argument validation (including extra="forbid") happens inside FastMCP, so a
    rejected call never reaches start_call and would be invisible in
    telemetry. Tool bodies catch their own errors, so any ToolError that
    escapes the manager is a rejection: invalid arguments or an unknown tool.

    The raw client arguments are also exposed to start_call so tool calls
    record what the client sent rather than every defaulted parameter.
    """
    manager = mcp._tool_manager
    call_tool = manager.call_tool

    async def call_tool_with_rejection_log(name, arguments, context=None, convert_result=False):
        token = set_client_arguments(arguments)
        try:
            return await call_tool(name, arguments, context=context, convert_result=convert_result)
        except ToolError as error:
            cause = error.__cause__
            status = "invalid_arguments" if isinstance(cause, ValidationError) else "rejected"
            start_call(name, arguments)
            if isinstance(cause, ValidationError):
                tool = manager.get_tool(name)
                valid = list((tool.parameters or {}).get("properties", {})) if tool else []
                details = describe_validation_error(cause, valid)
                record_arg_error(name, arguments, details)
                error = ToolError(format_arg_error(name, details, valid))
                error.__cause__ = cause
            _error_result(name, error, status=status)
            raise error
        finally:
            reset_client_arguments(token)

    manager.call_tool = call_tool_with_rejection_log


_record_rejected_tool_calls()

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


ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


def _issue_key(value: str, allow_numeric: bool = False) -> str:
    """Normalize and validate an issue key before any Backlog call."""
    key = str(value or "").strip().upper()
    if allow_numeric and key.isdigit():
        return key
    if not ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue key '{value}'. Expected a Backlog key such as 'OOP-123'.")
    configured = project_keys(get_config_instance())
    prefix = key.split("-")[0]
    if prefix not in configured:
        raise ValueError(f"Project '{prefix}' is not configured. Configured projects: {', '.join(configured)}")
    return key


def activate_workspace(workspace: str | None) -> dict | None:
    """Find and apply eval marker in workspace, then reload config singleton if needed.

    Returns the marker dict if found and applied, or None.
    If marker is applied, reloads the config singleton so it uses the fake backend URL.
    """
    from backlog_tool.settings import apply_eval_marker

    marker = find_eval_marker(workspace)
    if marker:
        apply_eval_marker(marker)
        # Reload the config singleton so it picks up the new env vars
        bootstrap_config()
    return marker


# Every tool talks to the live Backlog space. No write is idempotent: creating twice makes two
# issues and repeating an update adds its comment again; updates overwrite the fields they set.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_CREATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
_OVERWRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


@mcp.tool(annotations=_READ_ONLY)
def get_issue(
    issue_key: Annotated[str, Field(description="Backlog issue key such as 'OOP-123', or a numeric issue ID.")],
    view: Annotated[Literal["compact", "full"], Field(description="compact (default): the fields to work on the issue. full: the raw Backlog issue with every field.")] = "compact",
) -> CallToolResult:
    """Get one Backlog issue by key: everything needed to understand, investigate or fix it.

    Use when the user gives a Backlog issue key or link, e.g. to fix a bug.
    compact returns issueType, status, priority, assignee, createdUser (the reporter), dates, hours, url and custom fields.
    A bug report written in the template comes back parsed: description is its sections (environment,
    steps_to_reproduce, actual, expected, evidence...) with descriptionMeta, plus rawDescription when sections are missing.
    attachments lists the files (id, name, size, isImage); their content is not fetched.
    Do not use for discovery; use list_my_issues.
    """
    start_call("get_issue", locals())
    try:
        config = get_config_instance()
        issue_key = _issue_key(issue_key, allow_numeric=True)
        raw_issue = issue_service.get_issue(config, issue_key)
        if view == "full":
            data = raw_issue
        else:
            data = issue_context(raw_issue, base_url=view_base_url(config))
        return _build_result(data, "get_issue", project=project_key_from_issue_id(issue_key))
    except Exception as e:
        return _error_result("get_issue", e, project=project_key_from_issue_id(issue_key))


@mcp.tool(annotations=_READ_ONLY)
def list_my_issues(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    issue_types: Annotated[tuple[str, ...], Field(description="Issue type names to include: ['Bug'] for bugs, ['Story', 'Task'] for stories/tasks. Omit for every type.")] = (),
    query: Annotated[str, Field(description="Search keyword for issue summary or description. Omit or pass an empty string for no keyword filter.")] = "",
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
    """List Backlog issues assigned to the configured user in one project, with due-date context.

    Use when Backlog is explicitly invoked and the user asks for their bugs, stories/tasks, deadlines or what they have to do.
    Filter with issue_types (['Bug'] for open bugs); omit it for the combined personal status.
    This is a personal work view, not a PM/team/project-health dashboard.
    Items omit the description; get_issue returns it for the issue the user picks.
    Do not use to read one known issue; use get_issue.
    """
    start_call("list_my_issues", locals())
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("list_my_issues", e, project=project_key)

    try:
        config = get_config_instance()
        raw_issues = issue_service.list_my_issues(
            config,
            project_key=project_key or None,
            query=query or None,
            issue_types=list(issue_types) if issue_types else None,
            include_closed=include_closed,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            start_path=_workspace_path(),
        )
        base_url = view_base_url(config)
        data = [presenter.list_item(item, base_url=base_url) for item in raw_issues]
        return _build_result(
            data,
            "list_my_issues",
            list_key="issues",
            limit=limit,
            offset=offset,
            paginated=True,
            project=project_key,
            extra={"summary": presenter.list_summary(data)},
        )
    except Exception as e:
        return _error_result("list_my_issues", e, project=project_key)


@mcp.tool(annotations=_CREATES)
def create_issue(
    summary: Annotated[str, Field(description="Issue summary title")],
    issue_type: Annotated[str, Field(description="Issue type name or ID (e.g., 'Bug', 'Task', 'Story'). Required by Backlog for creation.")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    parent_key: Annotated[str, Field(description="Parent issue key such as 'OOP-123'. Omit or pass an empty string for no parent.")] = "",
    description: Annotated[str, Field(description="Issue description detail text. Omit or pass an empty string for no description.")] = "",
    priority: Annotated[str, Field(description="Priority name or ID (e.g., 'High', 'Normal', 'Low'). Omit for project default.")] = "",
    assignee: Annotated[str, Field(description="Assignee: 'me' or a numeric Backlog user ID. Omit to assign the issue to me.")] = "",
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
    Call with mode="apply" directly; the result lists every field set (changes: field, from, to).
    """
    start_call("create_issue", locals())
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        parent_key = _issue_key(parent_key) if parent_key.strip() else ""
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
        data = res if dry_run else _write_result(config, res, presenter.issue_changes(None, res))
        return _build_result(
            data,
            "create_issue",
            dry_run=dry_run,
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_issue", e, dry_run=dry_run, project=project_key)


@mcp.tool(annotations=_OVERWRITES)
def update_issue(
    issue_key: Annotated[str, Field(description="Backlog issue key such as 'OOP-123'.")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to infer from issue key or active workspace context.")] = "",
    summary: Annotated[str, Field(description="New issue summary title. Omit or pass an empty string to keep current summary.")] = "",
    status: Annotated[str, Field(description="Status name or ID to transition to. Omit to keep current status.")] = "",
    comment: Annotated[str, Field(description="Comment text to add to the update. Omit for no comment.")] = "",
    description: Annotated[str, Field(description="Replaces the whole description. To add a note, use comment instead. Omit to keep the current description.")] = "",
    priority: Annotated[str, Field(description="New priority name or ID. Omit to keep current priority.")] = "",
    assignee: Annotated[str, Field(description="New assignee: 'me' or a numeric Backlog user ID. Omit to keep the current assignee.")] = "",
    category: Annotated[str, Field(description="New category name or ID. Omit to keep current categories.")] = "",
    start_date: Annotated[str, Field(description="New start date in YYYY-MM-DD format. Omit to keep current start date.")] = "",
    due_date: Annotated[str, Field(description="New due date in YYYY-MM-DD format. Omit to keep current due date.")] = "",
    estimated_hours: Annotated[float | None, Field(description="New estimated hours. Omit to keep current value.")] = None,
    actual_hours: Annotated[float | None, Field(description="New actual hours. Omit to keep current value.")] = None,
    custom_fields: Annotated[dict[str, Any] | None, Field(description="Custom field updates keyed by configured custom field key.")] = None,
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned change without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Update arbitrary fields on an existing Backlog issue.

    Use when the user asks for explicit field changes outside a specialized personal workflow (escape hatch).
    Do not use to complete a bug resolution workflow; use resolve_bug.
    Call with mode="apply" directly; the result lists each changed field with its previous value (changes: field, from, to).
    """
    start_call("update_issue", locals())
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        issue_key = _issue_key(issue_key)
        # The previous values are what the user needs to check (or undo) an applied update.
        before = None if dry_run else issue_service.get_issue(config, issue_key)
        res = issue_service.update_issue(
            config,
            issue_id=issue_key,
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
        data = res if dry_run else _write_result(config, res, presenter.issue_changes(before, res, comment=comment))
        return _build_result(
            data,
            "update_issue",
            dry_run=dry_run,
            project=project_key or project_key_from_issue_id(issue_key),
        )
    except Exception as e:
        return _error_result(
            "update_issue",
            e,
            dry_run=dry_run,
            project=project_key or project_key_from_issue_id(issue_key),
        )


@mcp.tool(annotations=_OVERWRITES)
def resolve_bug(
    issue_key: Annotated[str, Field(description="Backlog issue key such as 'OOP-123'.")],
    status: Annotated[str, Field(description="Target status name or ID. Omit to use the configured resolved/closed status.")] = "",
    actual_hours: Annotated[float | None, Field(description="Actual hours spent fixing the bug. Used only when the issue has no actual hours yet; otherwise ignored with a warning. Omit when unknown.")] = None,
    estimated_hours: Annotated[float | None, Field(description="Estimated hours. Used only when the issue has no estimate yet; otherwise ignored with a warning. Omit when unknown.")] = None,
    qc_activity: Annotated[str, Field(description="Optional QC Activity option, used only when the issue field is empty (an existing value is kept and a warning is returned). Normally omit to apply the configured default.")] = "",
    cause_category: Annotated[str, Field(description="Optional Cause Category option such as 'CAR_Carelessness', used only when the issue field is empty (an existing value is kept and a warning is returned). Not a Bug Origin value. Normally omit to apply the configured default.")] = "",
    bug_origin: Annotated[str, Field(description="Optional Bug Origin option such as 'COD_Coding Logic', used only when the issue field is empty (an existing value is kept and a warning is returned). Normally omit to apply the configured default.")] = "",
    impacted: Annotated[str, Field(description="Optional configured Impacted-field override. Normally omit and let the workflow apply its configured value.")] = "",
    resolution: Annotated[str, Field(description="Optional Resolution value, used only when the issue field is empty. Omit to use the configured workflow value when applicable.")] = "",
    comment: Annotated[str, Field(description="Resolve comment text.")] = "",
    commit: Annotated[str, Field(description="Git commit hash/ref, only if the user gave it. Omit otherwise.")] = "",
    fix_description: Annotated[str, Field(description="What was changed, only if the user said it. Rendered into Corrective Action as 'fixed <text>' with casing preserved (write the object of 'fixed', e.g. 'OTP error message to include retry wait time'). Bulleted text renders as 'fixed:' followed by the bullets. Omit to use the bug summary.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned resolution without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Resolve a Backlog bug the user says is fixed, using the configured workflow defaults.

    Use when the user asks to resolve/close a Backlog bug or says it is already fixed.
    One call with mode="apply" does the whole resolution: it loads the issue, rules, field mappings
    and defaults and validates them itself, so no get_issue, get_bug_rules or get_bug_fields call is needed first.
    fix_description and commit are optional; without them the Corrective Action uses the bug summary.
    The result lists the changes (field, from, to) and any warnings; warnings never block.
    """
    start_call("resolve_bug", locals())
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        issue_key = _issue_key(issue_key)
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
        changes = bug_workflow.public_changes(res.get("changes", []))
        if dry_run:
            data = {"dryRun": True, "issue": res.get("issue"), "changes": changes, "warnings": res.get("warnings", [])}
        else:
            updated = res.get("updated") or {}
            base_url = view_base_url(config)
            data = {
                "issue": res.get("issue"),
                "status": (updated.get("status") or {}).get("name"),
                "assignee": (updated.get("assignee") or {}).get("name"),
                "url": f"{base_url.rstrip('/')}/view/{res.get('issue')}" if base_url else None,
                "changes": changes,
                "warnings": res.get("warnings", []),
            }
        return _build_result(
            data,
            "resolve_bug",
            dry_run=dry_run,
            project=project_key_from_issue_id(issue_key),
        )
    except Exception as e:
        return _error_result(
            "resolve_bug",
            e,
            dry_run=dry_run,
            project=project_key_from_issue_id(issue_key),
        )


@mcp.tool(annotations=_CREATES)
def create_ut_bug(
    parent_key: Annotated[str, Field(description="Parent issue key such as 'OOP-123' to attach the UT bug to.")],
    module: Annotated[str, Field(description="Name of the module or file with the failing unit test")],
    summary: Annotated[str, Field(description="Short title of the failure, e.g. 'total ignores discount'. Becomes '[<parent_key>][<module>] <summary>' and the Corrective Action.")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit to use the prefix of parent_key.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned bug without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Create a Unit Test Backlog sub-task bug under a parent issue.

    Use when the user explicitly asks Backlog to create a UT bug with configured workflow defaults.
    It loads and validates the parent itself, so no get_issue call is needed first.
    Do not use for generic bugs or tasks; use create_issue.
    Call with mode="apply" directly; the bug is created and closed at once, and the result lists every field set.
    """
    start_call("create_ut_bug", locals())
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        parent_key = _issue_key(parent_key)
        res = ut_bug.create_subtask_bug(
            config,
            project_key=project_key or None,
            parent_key=parent_key,
            module=module,
            summary=summary,
            dry_run=dry_run,
            start_path=_workspace_path(),
        )
        data = res if dry_run else _write_result(config, res["updated"], presenter.issue_changes(None, res["updated"]))
        return _build_result(
            data,
            "create_ut_bug",
            dry_run=dry_run,
            project=project_key or project_key_from_issue_id(parent_key),
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
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_ut_bug", e, dry_run=dry_run, project=project_key)


def _write_result(config, issue, changes):
    """What an applied create/update tells the model: which issue, and what it now says."""
    issue_key = (issue or {}).get("issueKey")
    return {"issueKey": issue_key, "url": f"{view_base_url(config)}/view/{issue_key}", "changes": changes}


def _support_project_key(project_key: str, issue_key: str) -> str:
    """Project for support tools: explicit key, else the prefix of a bug key."""
    issue_project = project_key_from_issue_id(issue_key) if issue_key else None
    if issue_key and not issue_project:
        raise ValueError(f"Invalid issue_key '{issue_key}'. Expected a Backlog key such as 'OOP-123'.")
    if project_key and issue_project and project_key != issue_project:
        raise ValueError(f"project_key '{project_key}' does not match issue_key '{issue_key}'.")
    return project_key or issue_project or ""


@mcp.tool(annotations=_READ_ONLY)
def get_bug_rules(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit when issue_key is given; otherwise resolved from the active workspace path or configuration.")] = "",
    issue_key: Annotated[str, Field(description="Bug issue key such as 'OOP-123' whose project rules/options to show. Preferred over project_key when working on a specific bug.")] = "",
) -> CallToolResult:
    """Inspect configured resolve-bug workflow rules for diagnostics or ambiguity.

    Use when the user asks for the rules or resolve_bug needs clarification; not a normal step before resolve_bug.
    """
    start_call("get_bug_rules", locals())
    project_key = project_key.strip().upper() or project_key_from_issue_id(issue_key.strip().upper()) or ""
    try:
        config = get_config_instance()
        issue_key = _issue_key(issue_key) if issue_key else ""
        project_key = _support_project_key(project_key, issue_key)
        data = guidance.resolve_rules(config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_rules", project=project_key)
    except Exception as e:
        return _error_result("get_bug_rules", e, project=project_key)


@mcp.tool(annotations=_READ_ONLY)
def get_bug_fields(
    field: Annotated[str, Field(description="Field name to get guidance for, e.g. qc_activity, bug_origin, cause_category. Omit for all fields.")] = "",
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit when issue_key is given; otherwise resolved from the active workspace path or configuration.")] = "",
    issue_key: Annotated[str, Field(description="Bug issue key such as 'OOP-123' whose project rules/options to show. Preferred over project_key when working on a specific bug.")] = "",
) -> CallToolResult:
    """Inspect allowed values/guidance for configured bug workflow fields.

    Use when a field is ambiguous, missing, or explicitly requested; not a normal step before resolve_bug.
    """
    start_call("get_bug_fields", locals())
    project_key = project_key.strip().upper() or project_key_from_issue_id(issue_key.strip().upper()) or ""
    try:
        config = get_config_instance()
        issue_key = _issue_key(issue_key) if issue_key else ""
        project_key = _support_project_key(project_key, issue_key)
        data = guidance.field_guidance(field or None, config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_fields", project=project_key)
    except Exception as e:
        return _error_result("get_bug_fields", e, project=project_key)


@mcp.resource(
    "backlog://issue/{issue_key}",
    mime_type="application/json",
    meta={"kind": "issue", "scope": "project"},
)
def issue_resource(issue_key: str) -> str:
    """Read one Backlog issue as JSON by issue key."""
    try:
        config = get_config_instance()
        data = issue_service.get_issue(config, _issue_key(issue_key, allow_numeric=True))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, indent=2, ensure_ascii=False)


def main() -> None:
    """Run the workstation-local server over stdio."""
    workspace = _workspace_path() or os.getcwd()
    marker = activate_workspace(workspace)
    tools = anyio.run(mcp.list_tools)
    log_session_start(backend="fake" if marker else "real", workspace=workspace, tool_count=len(tools))
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
