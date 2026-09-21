import os
from types import SimpleNamespace
from unittest import mock

import anyio
from mcp.types import CallToolResult, TextContent

from backlog_mcp import server
from backlog_tool import settings


def test_runtime_state_is_rooted_in_local_mcp_directory():
    assert settings.ENV_PATH == os.path.join(settings.MCP_ROOT, ".env")
    assert settings.LOG_DIR == os.path.join(settings.MCP_ROOT, "logs")
    assert settings.CONFIG_PATH == os.path.join(settings.MCP_ROOT, "config", "backlog.json")


def test_create_issue_previews_by_default():
    expected_result = CallToolResult(
        content=[TextContent(type="text", text="success")],
        structuredContent={"ok": True}
    )
    with mock.patch.object(server, "_invoke", return_value=expected_result) as invoke:
        result = server.create_issue("Summary", issue_type="Bug")

    assert result == expected_result
    args = invoke.call_args.args[0]
    assert args[:3] == ["issue", "create", "Summary"]
    assert "--issue-type" in args
    assert "--apply" not in args


def test_create_issue_applies_only_when_requested():
    with mock.patch.object(server, "_invoke") as invoke:
        server.create_issue("Summary", issue_type="Bug", mode="apply")

    assert invoke.call_args.args[0][-1] == "--apply"


def test_resolve_bug_previews_by_default_and_applies_when_requested():
    expected_result = CallToolResult(
        content=[TextContent(type="text", text="{}")],
        structuredContent={}
    )
    with mock.patch.object(server, "_invoke", return_value=expected_result) as invoke:
        server.resolve_bug("AQM-1")

    assert "--apply" not in invoke.call_args.args[0]

    with mock.patch.object(server, "_invoke", return_value=expected_result) as invoke:
        server.resolve_bug("AQM-1", mode="apply")

    assert invoke.call_args.args[0][-1] == "--apply"


def test_update_issue_and_create_ut_bug_preview_by_default():
    with mock.patch.object(server, "_invoke") as invoke:
        server.update_issue("AQM-1", summary="Updated")
        server.create_ut_bug("AQM-1", "module", "failure")

    for call in invoke.call_args_list:
        assert "--apply" not in call.args[0]


def test_inspect_project_does_not_write_by_default():
    expected_result = CallToolResult(
        content=[TextContent(type="text", text="{}")],
        structuredContent={}
    )
    with mock.patch.object(server, "_invoke", return_value=expected_result) as invoke:
        server.inspect_project("AQM")

    assert invoke.call_args.args[0] == ["project", "inspect", "AQM", "--stdout"]


def test_get_issues_maps_pagination_sort_and_field_selection():
    expected_result = CallToolResult(
        content=[TextContent(type="text", text="issues")],
        structuredContent={"ok": True}
    )
    with mock.patch.object(server, "_invoke", return_value=expected_result) as invoke:
        result = server.get_issues(
            project_key="AQM",
            query="payment",
            issue_types=("Bug",),
            limit=25,
            cursor="50",
            sort="updated",
            order="desc",
        )

    assert result == expected_result
    args = invoke.call_args.args[0]
    kwargs = invoke.call_args.kwargs
    assert args == [
        "issue", "list",
        "--limit", "25",
        "--offset", "50",
        "--sort", "updated",
        "--order", "desc",
        "--project", "AQM",
        "--query", "payment",
        "--type", "Bug",
        "--view", "compact",
    ]
    assert kwargs["paginated"] is True


def test_get_issues_with_invalid_cursor_returns_error():
    result = server.get_issues(cursor="invalid")
    assert result.isError is True
    assert "Invalid cursor format" in result.content[0].text


def test_invoke_returns_stable_success_envelope_with_pagination():
    command_result = SimpleNamespace(
        data=[{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}],
        text='[{"issueKey":"AQM-1"}]',
    )
    with mock.patch.object(server, "execute", return_value=command_result):
        result = server._invoke(
            ["issue", "list", "--limit", "1", "--offset", "0"],
            list_key="issues",
            limit=1,
            offset=0,
            paginated=True,
        )

    assert result.isError is False
    assert result.structuredContent == {
        "ok": True,
        "data": {"issues": [{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}]},
        "pagination": {
            "limit": 1,
            "nextCursor": "1",
            "hasMore": True,
        },
    }
    assert result.meta == {
        "command": "issue:list",
        "resourceUris": ["backlog://issue/AQM-1"],
    }
    assert "Retrieved 1 items via 'issue:list'." in result.content[0].text


def test_invoke_uses_claude_project_directory_as_workspace():
    command_result = SimpleNamespace(data=[], text="[]")
    with (
        mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/work/AQM"}, clear=True),
        mock.patch.object(server, "execute", return_value=command_result) as execute,
    ):
        server._invoke(["issue", "list"])

    execute.assert_called_once_with(["issue", "list"], workspace_path="/work/AQM")


def test_explicit_backlog_workspace_overrides_claude_project_directory():
    with mock.patch.dict(
        os.environ,
        {
            "BACKLOG_WORKSPACE_PATH": "/work/OOP",
            "CLAUDE_PROJECT_DIR": "/work/AQM",
        },
        clear=True,
    ):
        assert server._workspace_path() == "/work/OOP"


def test_invoke_returns_structured_error_without_raising():
    with mock.patch.object(server, "execute", side_effect=ValueError("bad field")):
        result = server._invoke(["issue", "update", "AQM-1"])

    assert result.isError is True
    assert result.structuredContent is None
    assert "Error: bad field" in result.content[0].text


def test_tool_schema_exposes_enums_and_use_when_descriptions():
    async def load_tools():
        return await server.mcp.list_tools()

    tools = {tool.name: tool for tool in anyio.run(load_tools)}
    get_issues = tools["get_issues"]
    get_issue = tools["get_issue"]
    create_issue = tools["create_issue"]

    assert "Use when" in get_issues.description
    assert "Do not use" in get_issues.description
    assert "view" not in get_issues.inputSchema["properties"]
    assert get_issue.inputSchema["properties"]["view"]["enum"] == ["compact", "full"]
    assert "cursor" in get_issues.inputSchema["properties"]
    assert "offset" not in get_issues.inputSchema["properties"]
    assert get_issues.inputSchema["properties"]["cursor"]["type"] == "string"
    for mutation_name in ("create_issue", "update_issue", "resolve_bug", "create_ut_bug"):
        mode_schema = tools[mutation_name].inputSchema["properties"]["mode"]
        assert mode_schema["enum"] == ["preview", "apply"]
        assert mode_schema["default"] == "preview"
    assert "workspace_path" not in create_issue.inputSchema["properties"]
    assert "parent" not in create_issue.inputSchema["properties"]
    assert "parent_key" in create_issue.inputSchema["properties"]
    assert create_issue.inputSchema["properties"]["project_key"]["default"] == ""
    assert "issue_type" in create_issue.inputSchema.get("required", [])


def test_resources_have_json_mime_type_and_issue_template():
    async def load_resources():
        return await server.mcp.list_resources(), await server.mcp.list_resource_templates()

    resources, templates = anyio.run(load_resources)
    resource_by_uri = {str(resource.uri): resource for resource in resources}
    template_by_uri = {template.uriTemplate: template for template in templates}

    assert resource_by_uri["backlog://config"].mimeType == "application/json"
    assert resource_by_uri["backlog://config"].meta == {"kind": "config", "scope": "workstation"}
    assert template_by_uri["backlog://issue/{issue_key}"].mimeType == "application/json"
    assert template_by_uri["backlog://issue/{issue_key}"].meta == {"kind": "issue", "scope": "project"}


def test_to_markdown_formatting():
    # Test formatting list of issues with status
    data_list = [
        {"issueKey": "PROJ-1", "summary": "Fix login issue", "status": "In Progress"},
        {"issueKey": "PROJ-2", "summary": "Design landing page", "status": "Open"}
    ]
    res_list = server._to_markdown(data_list, ["issue", "list"])
    assert "PROJ-1" in res_list
    assert "Fix login issue" in res_list
    assert "[In Progress]" in res_list
    assert "PROJ-2" in res_list
    assert "[Open]" in res_list

    # Test formatting single issue with status
    data_single = {"issueKey": "PROJ-123", "summary": "Database error", "status": "Closed"}
    res_single = server._to_markdown(data_single, ["issue", "get", "PROJ-123"])
    assert "PROJ-123" in res_single
    assert "Database error" in res_single
    assert "[Closed]" in res_single


def test_issue_compact_model_validation_and_normalization():
    # Test that _normalize_data correctly cleans and validates fields based on IssueCompact
    raw_data = {
        "issueKey": "PROJ-123",
        "summary": "Fix validation error",
        "description": "Details here",
        "issueType": "Bug",
        "status": "Open",
        "assignee": "Test User",
        "priority": "High",
        "startDate": None, # Should be excluded since it is None and we model_dump(exclude_none=True)
        "extraFieldToIgnore": "should_be_stripped", # Not in IssueCompact, should be ignored
        "customFields": [{"name": "QC", "value": "Unit Test"}]
    }

    normalized = server._normalize_data(raw_data, ["issue", "get", "PROJ-123"])
    assert normalized["issueKey"] == "PROJ-123"
    assert normalized["summary"] == "Fix validation error"
    assert normalized["description"] == "Details here"
    assert normalized["issueType"] == "Bug"
    assert normalized["status"] == "Open"
    assert normalized["assignee"] == "Test User"
    assert normalized["priority"] == "High"
    assert "startDate" not in normalized
    assert "extraFieldToIgnore" not in normalized
    assert normalized["customFields"] == [{"name": "QC", "value": "Unit Test"}]


def test_config_resource_excludes_sensitive_keys():
    import json
    raw_config = {
        "base_url": "https://bapjp.backlog.com",
        "api_key": "sensitive_api_key_123",
        "token": "sensitive_token",
        "projects": ["AQM"],
        "access_token": "abc",
        "refresh_token": "def",
        "client_secret": "secret123",
        "private_key": "private123",
        "backlog_api_key": "key123",
        "authToken": "token123",
        "author": "john_doe",
        "projectKey": "AQM",
        "nested": {
            "password": "my_password",
            "safe_field": "hello"
        }
    }
    with mock.patch("backlog_mcp.server.load_config", return_value=raw_config):
        res_json = server.config_resource()
        res = json.loads(res_json)
        assert "api_key" not in res
        assert "token" not in res
        assert "access_token" not in res
        assert "refresh_token" not in res
        assert "client_secret" not in res
        assert "private_key" not in res
        assert "backlog_api_key" not in res
        assert "authToken" not in res
        assert "password" not in res["nested"]
        assert res["author"] == "john_doe"
        assert res["projectKey"] == "AQM"
        assert res["nested"]["safe_field"] == "hello"
        assert res["base_url"] == "https://bapjp.backlog.com"


def test_issue_resource_success_and_error():
    import json
    
    # Test success scenario
    success_result = CallToolResult(
        content=[TextContent(type="text", text="issue details")],
        structuredContent={"issueKey": "AQM-1", "summary": "Fix issue"},
        isError=False
    )
    with mock.patch("backlog_mcp.server._invoke", return_value=success_result):
        res_json = server.issue_resource("AQM-1")
        res = json.loads(res_json)
        assert res["issueKey"] == "AQM-1"
        assert res["summary"] == "Fix issue"

    # Test error scenario
    error_result = CallToolResult(
        content=[TextContent(type="text", text="Error: Issue not found")],
        structuredContent=None,
        isError=True
    )
    with mock.patch("backlog_mcp.server._invoke", return_value=error_result):
        res_json = server.issue_resource("AQM-999")
        res = json.loads(res_json)
        assert res["ok"] is False
        assert res["error"] == "Issue not found"
