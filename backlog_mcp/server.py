#!/usr/bin/env python3
"""Stdio MCP server exposing the Backlog integration to every local project."""

import json
import os
from typing import Annotated, Any, Literal

import anyio
from pydantic import ConfigDict, Field, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase
from mcp.types import CallToolResult

from .arg_errors import describe_validation_error
from .results import _build_result, _error_result, _parse_cursor, _partial_write_result

from backlog_tool.settings import (
    load_config,
    load_env_file,
    project_keys,
    load_project_catalog,
    project_key_from_issue_id,
    view_base_url,
)
from backlog_tool import issue_service, presenter
from backlog_tool.resolver import resolve_user_id
from workflows import guidance, ut_bug, story_task_overview, personal_status
import workflows.resolve_bug as bug_workflow
from workflows.audit import audit_config
from backlog_tool.inspect import build_project_config, write_catalog
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


SERVER_INSTRUCTIONS = """This is a personal Backlog MCP for the configured user.

Activation:
- Use Backlog tools only when the user explicitly mentions Backlog/Backlog MCP, provides a Backlog issue key, or provides a Backlog URL.
- Do not route generic requests such as "what should I do?" or "project status" to Backlog without an activation signal.

Preferred tools:
- Personal status -> get_my_project_status
- My open bugs -> get_my_open_bugs
- Investigate/fix a specific bug -> get_bug_context
- Resolve/close a bug -> resolve_bug
- Generic get/search/update tools are escape hatches only.

Bug workflow:
- If the user says the bug is already fixed, use resolve_bug directly: preview -> apply.
- If the bug is not fixed yet, use get_bug_context first, then resolve_bug after the code fix.
- Do not pre-call get_issue, get_bug_rules, or get_bug_fields unless the specialized tool reports missing or ambiguous guidance.

Mutation safety:
- Preview mutations before apply.
- Apply only when the user explicitly requests the write.
- Do not add or change mutation fields after preview without previewing the final payload again.

Project resolution:
- Prefer an explicit project key.
- Otherwise resolve from workspace configuration/path only when unambiguous.
- If project resolution is ambiguous, fail instead of guessing.

Security:
- Never expose API keys or full request URLs containing query strings.
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
                record_arg_error(name, arguments, describe_validation_error(cause, valid))
            _error_result(name, error, status=status)
            raise
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


@mcp.tool()
def get_issue(
    issue_ref: Annotated[str, Field(description="Issue reference: Backlog issue key (e.g., 'PROJ-123') or numeric ID. Parameter name is issue_ref.")],
    view: Annotated[Literal["compact", "full"], Field(description="Detail level: compact for general triage, full for raw Backlog fields.")] = "compact",
) -> CallToolResult:
    """Get raw/current details of one Backlog issue by key or numeric ID.

    Use as an escape hatch for generic or non-bug Backlog issue inspection, or when raw fields are explicitly needed.
    Do not use as the first step for investigating or fixing a Bug; use get_bug_context instead.
    Do not use for discovery; use a personal domain list/status tool when possible.
    """
    start_call("get_issue", locals())
    try:
        config = get_config_instance()
        raw_issue = issue_service.get_issue(config, issue_ref)
        if view == "full":
            data = raw_issue
        else:
            base_url = view_base_url(config)
            data = presenter.compact_issue(raw_issue, view=view, base_url=base_url)
        return _build_result(data, "get_issue", project=project_key_from_issue_id(issue_ref))
    except Exception as e:
        return _error_result("get_issue", e, project=project_key_from_issue_id(issue_ref))


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
    """Run a custom Backlog issue search across issue types for the configured user.

    Use when the user explicitly needs custom Backlog filters/search that the personal domain tools do not provide; treat this as an escape hatch.
    Do not use for personal Backlog status; use get_my_project_status.
    Do not use for open personal bugs; use get_my_open_bugs.
    Do not use to investigate a specific bug; use get_bug_context.
    """
    start_call("get_issues", locals())
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_issues", e, project=project_key)

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
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_issues", e, project=project_key)


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
    start_call("create_issue", locals())
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
            dry_run=dry_run,
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_issue", e, dry_run=dry_run, project=project_key)


@mcp.tool()
def update_issue(
    issue_ref: Annotated[str, Field(description="Issue reference: Backlog issue key (e.g., 'PROJ-123') or numeric ID. Parameter name is issue_ref.")],
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
    """Update arbitrary fields on an existing Backlog issue.

    Use as an escape hatch for explicit field changes outside a specialized personal workflow.
    Do not use to complete a bug resolution workflow; use resolve_bug.
    """
    start_call("update_issue", locals())
    dry_run = (mode != "apply")
    try:
        config = get_config_instance()
        res = issue_service.update_issue(
            config,
            issue_id=issue_ref,
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
            dry_run=dry_run,
            project=project_key or project_key_from_issue_id(issue_ref),
        )
    except Exception as e:
        return _error_result(
            "update_issue",
            e,
            dry_run=dry_run,
            project=project_key or project_key_from_issue_id(issue_ref),
        )


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
    """List open Backlog bugs assigned to the configured user in one project.

    Use when Backlog is explicitly invoked and the user asks for their current bugs/bug queue.
    Prefer this one-call personal workflow over generic get_issues filtering.
    """
    start_call("get_my_open_bugs", locals())
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_my_open_bugs", e, project=project_key)

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
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_my_open_bugs", e, project=project_key)


@mcp.tool()
def get_bug_context(
    issue_key: Annotated[str, Field(description="Bug issue key (e.g., 'PRJ-123') to analyze. Parameter name is issue_key (snake_case).")],
) -> CallToolResult:
    """Get AI-ready Backlog context for a specific bug.

    This is the primary entry point when a Backlog bug key/link is supplied and the user wants to understand, investigate, fix, discuss, or prepare to resolve it.
    Do not call get_issue first just to inspect the same bug.
    Do not use for listing bugs; use get_my_open_bugs.
    """
    start_call("get_bug_context", locals())
    try:
        config = get_config_instance()
        data = bug_workflow.get_bug_context(config, issue_key)
        return _build_result(data, "get_bug_context", project=project_key_from_issue_id(issue_key))
    except Exception as e:
        return _error_result("get_bug_context", e, project=project_key_from_issue_id(issue_key))


@mcp.tool()
def resolve_bug(
    issue_key: Annotated[str, Field(description="Bug issue key to resolve (e.g., 'PRJ-123'). Parameter name is issue_key (snake_case).")],
    status: Annotated[str, Field(description="Target status name or ID. Omit to use the configured resolved/closed status.")] = "",
    actual_hours: Annotated[float | None, Field(description="Actual hours spent fixing the bug. Used only when the issue has no actual hours yet; otherwise ignored with a warning. Omit when unknown.")] = None,
    estimated_hours: Annotated[float | None, Field(description="Estimated hours. Used only when the issue has no estimate yet; otherwise ignored with a warning. Omit when unknown.")] = None,
    qc_activity: Annotated[str, Field(description="Optional QC Activity option, used only when the issue field is empty (an existing value is kept and a warning is returned). Normally omit to apply the configured default.")] = "",
    cause_category: Annotated[str, Field(description="Optional Cause Category option such as 'CAR_Carelessness', used only when the issue field is empty (an existing value is kept and a warning is returned). Not a Bug Origin value. Normally omit to apply the configured default.")] = "",
    bug_origin: Annotated[str, Field(description="Optional Bug Origin option such as 'COD_Coding Logic', used only when the issue field is empty (an existing value is kept and a warning is returned). Normally omit to apply the configured default.")] = "",
    impacted: Annotated[str, Field(description="Optional configured Impacted-field override. Normally omit and let the workflow apply its configured value.")] = "",
    resolution: Annotated[str, Field(description="Optional Resolution value, used only when the issue field is empty. Omit to use the configured workflow value when applicable.")] = "",
    comment: Annotated[str, Field(description="Resolve comment text.")] = "",
    commit: Annotated[str, Field(description="Git commit hash/ref related to the fix.")] = "",
    fix_description: Annotated[str, Field(description="What was changed to fix the bug. Rendered into Corrective Action as 'fixed <text>' with casing preserved, so write the object of 'fixed' (e.g. 'OTP error message to include retry wait time'), not a sentence starting with a verb. Bulleted text renders as 'fixed:' followed by the bullets. Required in apply mode.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned resolution without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Resolve a Backlog bug using the configured business workflow and defaults.

    Use when the user explicitly asks to resolve/close a specific Backlog bug.
    The workflow already loads issue context, rules, field mappings, defaults, and validation internally.
    Preview once with the final arguments, then apply with the same arguments after confirmation; do not repeat an identical preview.
    Do not pre-call get_bug_rules or get_bug_fields unless resolve_bug reports ambiguity/missing guidance.
    Do not use for unrelated generic issue updates; use update_issue.
    """
    start_call("resolve_bug", locals())
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


@mcp.tool()
def create_ut_bug(
    parent_key: Annotated[str, Field(description="Parent issue key (e.g., 'PRJ-123') to attach the UT bug to")],
    module: Annotated[str, Field(description="Name of the module or file with the failing unit test")],
    description: Annotated[str, Field(description="Unit test failure description details")],
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace path or configuration.")] = "",
    mode: Annotated[MutationMode, Field(description="Execution mode: preview returns the planned bug without writing; apply submits it to Backlog.")] = "preview",
) -> CallToolResult:
    """Create a Unit Test Backlog sub-task bug under a parent issue.

    Use when the user explicitly asks Backlog to create a UT bug with configured workflow defaults.
    The workflow validates/loads the parent internally; do not call get_issue first just to prepare this action.
    Do not use for generic bugs or tasks; use create_issue.
    """
    start_call("create_ut_bug", locals())
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
            project=project_key,
        )
    except Exception as e:
        return _error_result("create_ut_bug", e, dry_run=dry_run, project=project_key)


def _support_project_key(project_key: str, issue_key: str) -> str:
    """Project for support tools: explicit key, else the prefix of a bug key."""
    issue_project = project_key_from_issue_id(issue_key) if issue_key else None
    if issue_key and not issue_project:
        raise ValueError(f"Invalid issue_key '{issue_key}'. Expected a Backlog key such as 'PRJ-123'.")
    if project_key and issue_project and project_key != issue_project:
        raise ValueError(f"project_key '{project_key}' does not match issue_key '{issue_key}'.")
    return project_key or issue_project or ""


@mcp.tool()
def get_bug_rules(
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit when issue_key is given; otherwise resolved from the active workspace path or configuration.")] = "",
    issue_key: Annotated[str, Field(description="Bug issue key (e.g., 'PRJ-123') whose project rules to show. Preferred over project_key when working on a specific bug.")] = "",
) -> CallToolResult:
    """Inspect configured resolve-bug workflow rules for diagnostics or ambiguity.

    This is a support/debug tool, not a normal step before resolve_bug.
    Use only when the user asks for the rules or resolve_bug needs clarification.
    """
    start_call("get_bug_rules", locals())
    project_key = project_key or project_key_from_issue_id(issue_key) or ""
    try:
        config = get_config_instance()
        project_key = _support_project_key(project_key, issue_key)
        data = guidance.resolve_rules(config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_rules", project=project_key)
    except Exception as e:
        return _error_result("get_bug_rules", e, project=project_key)


@mcp.tool()
def get_bug_fields(
    field: Annotated[str, Field(description="Field name to get guidance for, e.g. qc_activity, bug_origin, cause_category. Omit for all fields.")] = "",
    project_key: Annotated[str, Field(description="Project key (e.g., 'PRJ'). Omit when issue_key is given; otherwise resolved from the active workspace path or configuration.")] = "",
    issue_key: Annotated[str, Field(description="Bug issue key (e.g., 'PRJ-123') whose project field options to show. Preferred over project_key when working on a specific bug.")] = "",
) -> CallToolResult:
    """Inspect allowed values/guidance for configured bug workflow fields.

    This is a support/debug tool, not a normal step before resolve_bug.
    Use only when a field is ambiguous, missing, or explicitly requested.
    """
    start_call("get_bug_fields", locals())
    project_key = project_key or project_key_from_issue_id(issue_key) or ""
    try:
        config = get_config_instance()
        project_key = _support_project_key(project_key, issue_key)
        data = guidance.field_guidance(field or None, config, project_key or None, start_path=_workspace_path())
        return _build_result(data, "get_bug_fields", project=project_key)
    except Exception as e:
        return _error_result("get_bug_fields", e, project=project_key)


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
    """List the configured user's Backlog Stories and Tasks with due-date/status context.

    Use when Backlog is explicitly invoked and the user specifically asks for Stories/Tasks or deadlines.
    For the broader personal Backlog status including bugs, prefer get_my_project_status.
    """
    start_call("get_my_work_overview", locals())
    try:
        offset = _parse_cursor(cursor)
    except ValueError as e:
        return _error_result("get_my_work_overview", e, project=project_key)

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
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_my_work_overview", e, project=project_key)


@mcp.tool()
def get_my_project_status(
    project_key: Annotated[str, Field(description="Backlog project key (e.g., 'PRJ'). Omit or pass an empty string to resolve from the active workspace.")]= "",
) -> CallToolResult:
    """Get one personal Backlog status view for the configured user in a project.

    Use when Backlog is explicitly invoked and the user asks what they have to do, their Backlog/project status, or a combined view of current personal work.
    This is a personal work view, not a PM/team/project-health dashboard.
    It combines assigned Stories/Tasks and open Bugs in one MCP call.
    """
    start_call("get_my_project_status", locals())
    try:
        config = get_config_instance()
        data = personal_status.get_my_project_status(
            config,
            project_key=project_key or None,
            start_path=_workspace_path(),
        )
        return _build_result(
            data,
            "get_my_project_status",
            project=project_key,
        )
    except Exception as e:
        return _error_result("get_my_project_status", e, project=project_key)


@mcp.tool()
def list_configured_projects() -> CallToolResult:
    """List configured Backlog projects without querying every project.

    Use when choosing or confirming a project key.
    Do not use to fetch live project metadata; use inspect_project for one explicit project.
    """
    start_call("list_configured_projects", locals())
    try:
        config = get_config_instance()
        rows = []
        for key in project_keys(config):
            try:
                catalog = load_project_catalog(key)
                rows.append({"key": key, "id": catalog.get("id"), "name": catalog.get("name")})
            except Exception:
                rows.append({"key": key, "id": None, "name": "(missing catalog)"})
        return _build_result(rows, "list_configured_projects", list_key="projects")
    except Exception as e:
        return _error_result("list_configured_projects", e)


@mcp.tool()
def get_config() -> CallToolResult:
    """Get local Backlog configuration settings with credentials excluded.

    Use when diagnosing local MCP configuration or defaults.
    Do not use to retrieve secrets; credentials are intentionally excluded.
    """
    start_call("get_config", locals())
    try:
        config = get_config_instance()
        return _build_result(redact_config(config), "get_config")
    except Exception as e:
        return _error_result("get_config", e)


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
    start_call("audit_config_workflows", locals())
    try:
        config = get_config_instance()
        data = audit_config(config, mode=mode)
        return _build_result(data, "audit_config_workflows")
    except Exception as e:
        return _error_result("audit_config_workflows", e)


@mcp.tool()
def inspect_project(
    project_key: Annotated[str, Field(description="Project key to inspect (e.g., 'PRJ')")],
    mode: Annotated[Literal["read", "refresh_catalog"], Field(description="read fetches metadata without writing; refresh_catalog writes the local project catalog.")] = "read",
) -> CallToolResult:
    """Fetch project metadata or refresh one local project catalog.

    Use when the user names one project and needs its metadata or catalog refreshed.
    Do not use to enumerate every project; use list_configured_projects.
    """
    start_call("inspect_project", locals())
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
            project=project_key,
        )
    except Exception as e:
        return _error_result("inspect_project", e, project=project_key)


@mcp.prompt()
def resolve_bug_prompt(
    issue_key: Annotated[str, Field(description="The key of the bug issue to resolve (e.g., 'PRJ-123')")]
) -> str:
    """Guide the agent to resolve a bug following project workflow policies."""
    return (
        f"Resolve Backlog bug {issue_key} using the configured personal workflow.\n\n"
        f"Normal path:\n"
        f"1. Call `resolve_bug` in preview mode once, with `fix_description` describing the change. The tool already loads issue context, workflow rules, mappings, defaults, and validation.\n"
        f"2. Review preview changes/warnings. Only call `get_bug_fields` or `get_bug_rules` if preview reports ambiguity/missing guidance or the user asks for those details.\n"
        f"3. Call `resolve_bug` in apply mode with the same arguments only after the user has explicitly requested/confirmed the write."
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
        f"Create a Backlog Unit Test (UT) child bug for parent {parent_key} and module {module}.\n"
        f"Current failure description: {desc_val}\n\n"
        f"Normal path:\n"
        f"1. If the failure description is missing, ask for/draft it from the existing coding context.\n"
        f"2. Call `create_ut_bug` in preview mode; it loads and validates the parent internally.\n"
        f"3. Review the preview, then call `create_ut_bug` in apply mode only after explicit write confirmation."
    )


@mcp.prompt()
def project_status_prompt(
    project: Annotated[str, Field(description="Project key. Omit only when the active workspace can resolve the project unambiguously; otherwise the tool should return an error.")] = ""
) -> str:
    """Guide the agent to check the current project status overview."""
    proj_desc = f"project '{project}'" if project else "the active workspace"
    return (
        f"Check my personal Backlog status for {proj_desc}.\n\n"
        f"Use `get_my_project_status` once. It combines my assigned Stories/Tasks, deadlines, and open Bugs. "
        f"This is my personal work view, not a team/PM project-health report. "
        f"If the project is omitted and cannot be resolved unambiguously, stop instead of guessing."
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
    tools = anyio.run(mcp.list_tools)
    log_session_start(backend="real", workspace=_workspace_path() or os.getcwd(), tool_count=len(tools))
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
