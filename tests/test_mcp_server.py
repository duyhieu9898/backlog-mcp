import json
import os
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
    with mock.patch("backlog_mcp.server.issue_service.create_issue", return_value={"dryRun": True, "payload": {}}) as create_mock:
        result = server.create_issue("Summary", issue_type="Bug")

    assert result.isError is False
    assert create_mock.call_args.kwargs["dry_run"] is True
    assert create_mock.call_args.kwargs["summary"] == "Summary"
    assert create_mock.call_args.kwargs["issue_type"] == "Bug"


def test_create_issue_applies_only_when_requested():
    with mock.patch("backlog_mcp.server.issue_service.create_issue", return_value={"id": 123, "issueKey": "AQM-1"}) as create_mock:
        server.create_issue("Summary", issue_type="Bug", mode="apply")

    assert create_mock.call_args.kwargs["dry_run"] is False


def test_resolve_bug_previews_by_default_and_applies_when_requested():
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value={"dryRun": True, "issue": "AQM-1"}) as resolve_mock:
        server.resolve_bug("AQM-1")
    assert resolve_mock.call_args.kwargs["dry_run"] is True

    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value={"issueKey": "AQM-1"}) as resolve_mock:
        server.resolve_bug("AQM-1", mode="apply")
    assert resolve_mock.call_args.kwargs["dry_run"] is False


def test_update_issue_and_create_ut_bug_preview_by_default():
    with mock.patch("backlog_mcp.server.issue_service.update_issue", return_value={"dryRun": True}) as update_mock, \
         mock.patch("backlog_mcp.server.ut_bug.create_subtask_bug", return_value={"dryRun": True}) as ut_mock:
        server.update_issue("AQM-1", summary="Updated")
        server.create_ut_bug("AQM-1", "module", "failure")

    assert update_mock.call_args.kwargs["dry_run"] is True
    assert ut_mock.call_args.kwargs["dry_run"] is True


def test_inspect_project_does_not_write_by_default():
    with mock.patch("backlog_mcp.server.build_project_config", return_value={"key": "AQM"}) as build_mock, \
         mock.patch("backlog_mcp.server.write_catalog") as write_mock:
        server.inspect_project("AQM")

    build_mock.assert_called_once()
    write_mock.assert_not_called()


def test_get_issues_maps_pagination_sort_and_field_selection():
    with mock.patch("backlog_mcp.server.issue_service.get_issues", return_value=[]) as get_mock:
        result = server.get_issues(
            project_key="AQM",
            query="payment",
            issue_types=("Bug",),
            limit=25,
            cursor="50",
            sort="updated",
            order="desc",
        )

    assert result.isError is False
    kwargs = get_mock.call_args.kwargs
    assert kwargs["project_key"] == "AQM"
    assert kwargs["query"] == "payment"
    assert kwargs["issue_types"] == ["Bug"]
    assert kwargs["limit"] == 25
    assert kwargs["offset"] == 50
    assert kwargs["sort"] == "updated"
    assert kwargs["order"] == "desc"


def test_get_issues_with_invalid_cursor_returns_error():
    result = server.get_issues(cursor="invalid")
    assert result.isError is True
    assert "Invalid cursor format" in result.content[0].text


def test_build_result_returns_stable_success_envelope_with_pagination():
    data = [{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}]
    result = server._build_result(
        data,
        tool="get_issues",
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
        "tool": "get_issues",
        "command": "get_issues",
        "resourceUris": ["backlog://issue/AQM-1"],
    }
    assert "Retrieved 1 items via 'get_issues'." in result.content[0].text


def test_server_uses_claude_project_directory_as_workspace():
    with (
        mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/work/AQM"}, clear=True),
        mock.patch("backlog_mcp.server.issue_service.get_issues", return_value=[]) as get_mock,
    ):
        server.get_issues(project_key="AQM")

    assert get_mock.call_args.kwargs["start_path"] == "/work/AQM"


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


def test_error_result_returns_structured_error_without_raising():
    result = server._error_result("update_issue", ValueError("bad field"))

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
    res_list = server._to_markdown(data_list, "get_issues")
    assert "PROJ-1" in res_list
    assert "Fix login issue" in res_list
    assert "[In Progress]" in res_list
    assert "PROJ-2" in res_list
    assert "[Open]" in res_list

    # Test formatting single issue with status
    data_single = {"issueKey": "PROJ-123", "summary": "Database error", "status": "Closed"}
    res_single = server._to_markdown(data_single, "get_issue")
    assert "PROJ-123" in res_single
    assert "Database error" in res_single
    assert "[Closed]" in res_single


def test_tool_execution_logs_metrics_on_success_and_error():
    with mock.patch("backlog_mcp.server.log_metric") as log_metric_mock, \
         mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", return_value={"issueKey": "AQM-1"}):
        result = server.get_bug_context("AQM-1")
        assert result.isError is False
        log_metric_mock.assert_called_once()
        call_args = log_metric_mock.call_args
        assert call_args.args[0] == "get_bug_context"
        assert call_args.args[3] == "ok"

    with mock.patch("backlog_mcp.server.log_metric") as log_metric_mock, \
         mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", side_effect=ValueError("Boom")):
        result = server.get_bug_context("AQM-1")
        assert result.isError is True
        log_metric_mock.assert_called_once()
        call_args = log_metric_mock.call_args
        assert call_args.args[0] == "get_bug_context"
        assert call_args.args[3] == "error"


def test_config_resource_excludes_sensitive_keys():
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
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value={"issueKey": "AQM-1", "summary": "Fix issue"}):
        res_json = server.issue_resource("AQM-1")
        res = json.loads(res_json)
        assert res["issueKey"] == "AQM-1"
        assert res["summary"] == "Fix issue"

    with mock.patch("backlog_mcp.server.issue_service.get_issue", side_effect=ValueError("Issue not found")):
        res_json = server.issue_resource("AQM-999")
        res = json.loads(res_json)
        assert res["ok"] is False
        assert res["error"] == "Issue not found"


def test_create_ut_bug_returns_structured_partial_write_error():
    error = server.ut_bug.PostCreateUpdateError(
        "AQM-123",
        {"statusId": 4, "assigneeId": 9},
        "Closed",
        RuntimeError("update failed"),
    )
    with mock.patch(
        "backlog_mcp.server.ut_bug.create_subtask_bug",
        side_effect=error,
    ):
        result = server.create_ut_bug(
            parent_key="AQM-1",
            module="payments",
            description="fails",
            project_key="AQM",
            mode="apply",
        )

    assert result.isError is True
    assert result.structuredContent["ok"] is False
    detail = result.structuredContent["error"]
    assert detail["kind"] == "partial_write"
    assert detail["issueKey"] == "AQM-123"
    assert detail["committed"] == {"created": True, "postCreateUpdate": False}
    assert detail["recovery"]["targetStatus"] == "Closed"
    assert detail["recovery"]["updatePayload"] == {"statusId": 4, "assigneeId": 9}
