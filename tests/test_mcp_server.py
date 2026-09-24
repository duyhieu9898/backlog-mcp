import json
import os
from unittest import mock

import anyio
import pytest
from mcp.types import CallToolResult, TextContent

from backlog_mcp import server
from backlog_mcp.results import _to_markdown
from backlog_tool import settings


@pytest.mark.real_log_paths
def test_runtime_state_is_rooted_in_local_mcp_directory():
    assert settings.ENV_PATH == os.path.join(settings.MCP_ROOT, ".env")
    assert settings.LOG_DIR == os.path.join(settings.MCP_ROOT, "logs")
    assert settings.CONFIG_PATH == os.path.join(settings.MCP_ROOT, "config", "backlog.json")



def test_get_config_instance_surfaces_bootstrap_error_without_silent_retry():
    original_config = server._config
    original_error = server._bootstrap_error
    try:
        server._config = None
        server._bootstrap_error = ValueError("bad config")

        with mock.patch("backlog_mcp.server.bootstrap_config") as bootstrap_mock:
            try:
                server.get_config_instance()
                assert False, "expected startup config error"
            except RuntimeError as error:
                assert "configuration failed to load" in str(error)
                assert "bad config" in str(error)

        bootstrap_mock.assert_not_called()
    finally:
        server._config = original_config
        server._bootstrap_error = original_error

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
    from backlog_tool import telemetry

    data = [{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}]
    telemetry.start_call("get_issues", {})
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
    assert result.meta["tool"] == "get_issues"
    assert result.meta["command"] == "get_issues"
    assert result.meta["resourceUris"] == ["backlog://issue/AQM-1"]
    assert result.meta["traceId"]
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
    update_issue = tools["update_issue"]
    get_bug_context = tools["get_bug_context"]
    resolve_bug = tools["resolve_bug"]
    create_issue = tools["create_issue"]
    audit_tool = tools["audit_config_workflows"]

    assert "Use when" in get_issues.description
    assert "Do not use" in get_issues.description
    assert "view" not in get_issues.inputSchema["properties"]
    assert get_issue.inputSchema["properties"]["view"]["enum"] == ["compact", "full"]
    assert "issue_ref" in get_issue.inputSchema["properties"]
    assert "issue_id" not in get_issue.inputSchema["properties"]
    assert "issueKey" not in get_issue.inputSchema["properties"]
    assert "issue_ref" in update_issue.inputSchema["properties"]
    assert "issue_id" not in update_issue.inputSchema["properties"]
    assert "issue_key" in get_bug_context.inputSchema["properties"]
    assert "issueKey" not in get_bug_context.inputSchema["properties"]
    assert "snake_case" in get_bug_context.inputSchema["properties"]["issue_key"]["description"]
    assert "issue_key" in resolve_bug.inputSchema["properties"]
    assert "issueKey" not in resolve_bug.inputSchema["properties"]
    assert "snake_case" in resolve_bug.inputSchema["properties"]["issue_key"]["description"]
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
    assert audit_tool.inputSchema["properties"]["mode"]["enum"] == ["local", "live"]
    assert audit_tool.inputSchema["properties"]["mode"]["default"] == "local"



def test_tool_argument_models_reject_unknown_fields():
    resolve_tool = server.mcp._tool_manager.get_tool("resolve_bug")

    with pytest.raises(Exception) as error:
        resolve_tool.fn_metadata.arg_model.model_validate(
            {"issue_key": "OOP-12757", "dry_run": False}
        )

    assert "extra" in str(error.value).lower()
    assert "dry_run" in str(error.value)

    with pytest.raises(Exception) as error:
        resolve_tool.fn_metadata.arg_model.model_validate(
            {"issue_key": "OOP-12757", "resolution_summary": "fixed"}
        )

    assert "extra" in str(error.value).lower()
    assert "resolution_summary" in str(error.value)


def test_tool_schemas_disallow_additional_properties():
    async def load_tools():
        return await server.mcp.list_tools()

    tools = {tool.name: tool for tool in anyio.run(load_tools)}
    assert tools["resolve_bug"].inputSchema["additionalProperties"] is False
    assert tools["get_bug_context"].inputSchema["additionalProperties"] is False
    assert tools["get_issue"].inputSchema["additionalProperties"] is False

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
    res_list = _to_markdown(data_list, "get_issues")
    assert "PROJ-1" in res_list
    assert "Fix login issue" in res_list
    assert "[In Progress]" in res_list
    assert "PROJ-2" in res_list
    assert "[Open]" in res_list

    # Test formatting single issue with status
    data_single = {"issueKey": "PROJ-123", "summary": "Database error", "status": "Closed"}
    res_single = _to_markdown(data_single, "get_issue")
    assert "PROJ-123" in res_single
    assert "Database error" in res_single
    assert "[Closed]" in res_single


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
    assert detail["retrySafe"] is False
    assert detail["recovery"]["action"] == "update_existing_issue"
    assert detail["recovery"]["issueKey"] == "AQM-123"
    assert detail["recovery"]["targetStatus"] == "Closed"
    assert detail["recovery"]["updatePayload"] == {"statusId": 4, "assigneeId": 9}


def test_audit_config_workflows_live_mode_is_read_only():
    with mock.patch(
        "backlog_mcp.server.audit_config",
        return_value={
            "ok": False,
            "mode": "live",
            "changedProjects": ["AQM"],
            "projects": [],
            "writesPerformed": False,
        },
    ) as audit_mock:
        result = server.audit_config_workflows(mode="live")

    assert result.isError is False
    audit_mock.assert_called_once_with(server.get_config_instance(), mode="live")
    assert result.structuredContent["data"]["writesPerformed"] is False


def test_personal_project_status_aggregates_work_and_bugs_in_one_tool():
    with mock.patch(
        "backlog_mcp.server.personal_status.get_my_project_status",
        return_value={
            "storiesAndTasks": [{"issueKey": "OOP-1"}],
            "openBugs": [{"issueKey": "OOP-2"}],
            "summary": {
                "storyTaskCount": 1,
                "openBugCount": 1,
                "overdueCount": 0,
                "dueSoonCount": 0,
            },
        },
    ) as status_mock:
        result = server.get_my_project_status("OOP")

    assert result.isError is False
    assert result.structuredContent["data"]["summary"]["openBugCount"] == 1
    status_mock.assert_called_once_with(
        server.get_config_instance(),
        project_key="OOP",
        start_path=server._workspace_path(),
    )


def test_personal_routing_contract_is_explicit_and_domain_first():
    async def load_tools():
        return await server.mcp.list_tools()

    tools = {tool.name: tool for tool in anyio.run(load_tools)}

    assert "Backlog is explicitly invoked" in tools["get_my_project_status"].description
    assert "not a PM/team/project-health dashboard" in tools["get_my_project_status"].description
    assert "Do not call get_issue first" in tools["get_bug_context"].description
    assert "Do not pre-call get_bug_rules or get_bug_fields" in tools["resolve_bug"].description
    assert "escape hatch" in tools["get_issues"].description
    assert "personal Backlog status" in tools["get_issues"].description


def test_server_instructions_require_backlog_activation_and_minimal_bug_paths():
    instructions = server.SERVER_INSTRUCTIONS.lower()
    assert "activation:" in instructions
    assert "provides a backlog issue key" in instructions
    assert "without an activation signal" in instructions
    assert "resolve/close a bug -> resolve_bug" in instructions
    assert "already fixed" in instructions
    assert "use resolve_bug directly: preview -> apply" in instructions
    assert "not fixed yet" in instructions
    assert "use get_bug_context first" in instructions
    assert "do not pre-call get_issue, get_bug_rules, or get_bug_fields" in instructions
    assert "do not add or change mutation fields after preview" in instructions
    assert "previewing the final payload again" in instructions
    assert "read before mutating" not in instructions


def test_personal_prompts_use_minimal_domain_paths():
    resolve_prompt = server.resolve_bug_prompt("OOP-123")
    assert "resolve_bug" in resolve_prompt
    assert "Call `get_bug_context`" not in resolve_prompt
    assert "Call `get_bug_rules`" not in resolve_prompt
    assert "Call `get_bug_fields`" not in resolve_prompt

    ut_prompt = server.create_ut_bug_prompt("OOP-1", "admin", "fails")
    assert "create_ut_bug" in ut_prompt
    assert "get_issue" not in ut_prompt

    status_prompt = server.project_status_prompt("OOP")
    assert "get_my_project_status" in status_prompt
    assert "get_my_work_overview" not in status_prompt
    assert "get_my_open_bugs" not in status_prompt


def test_bug_support_tools_resolve_project_from_issue_key():
    with mock.patch("backlog_mcp.server.guidance.resolve_rules", return_value={"ok": True}) as rules:
        result = server.get_bug_rules(issue_key="OOP-12760")
    assert result.isError is False
    assert rules.call_args.args[1] == "OOP"

    with mock.patch("backlog_mcp.server.guidance.field_guidance", return_value={"ok": True}) as fields:
        result = server.get_bug_fields("cause_category", issue_key="OOP-12760")
    assert result.isError is False
    assert fields.call_args.args[2] == "OOP"

    result = server.get_bug_rules(project_key="AQM", issue_key="OOP-12760")
    assert result.isError is True
    assert "does not match" in result.content[0].text


def test_client_metadata_uses_mcp_client_info(monkeypatch):
    from types import SimpleNamespace

    from mcp.server.lowlevel.server import request_ctx
    from backlog_tool import telemetry

    monkeypatch.delenv("BACKLOG_MCP_CLIENT", raising=False)
    monkeypatch.delenv("BACKLOG_MCP_CLIENT_VERSION", raising=False)
    assert telemetry.client_metadata()["name"] == "unknown"

    session = SimpleNamespace(client_params=SimpleNamespace(clientInfo=SimpleNamespace(name="claude-code", version="2.1")))
    token = request_ctx.set(SimpleNamespace(session=session))
    try:
        assert telemetry.client_metadata()["name"] == "claude-code"
        assert telemetry.client_metadata()["version"] == "2.1"
        monkeypatch.setenv("BACKLOG_MCP_CLIENT", "override")
        assert telemetry.client_metadata()["name"] == "override"
    finally:
        request_ctx.reset(token)


from backlog_tool import telemetry


def _rows(kind):
    path = telemetry.log_paths()[kind]
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _details():
    folder = telemetry.log_paths()["details_dir"]
    rows = []
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            rows += [json.loads(line) for line in handle if line.strip()]
    return rows


def test_tool_success_and_error_are_logged_with_project_from_issue_key():
    with mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", return_value={"issueKey": "OOP-1"}):
        ok = server.get_bug_context("OOP-1")
    with mock.patch("backlog_mcp.server.bug_workflow.get_bug_context", side_effect=ValueError("Boom")):
        bad = server.get_bug_context("OOP-1")

    first, second = _rows("calls")
    assert (first["tool"], first["status"], first["projectKey"]) == ("get_bug_context", "ok", "OOP")
    assert (second["status"], second["projectKey"]) == ("error", "OOP")
    assert ok.meta["traceId"] == first["traceId"] and bad.meta["traceId"] == second["traceId"]
    assert _rows("errors")[0]["message"] == "Boom"
    assert _details()[0]["result"] == ok.structuredContent
    assert _details()[0]["text"] == ok.content[0].text


def test_response_bytes_count_full_serialized_result():
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value={"issueKey": "OOP-1", "description": "x" * 2000}):
        server.get_issue("OOP-1", view="full")
    call = _rows("calls")[0]
    assert call["responseBytes"] > 2000 and call["estTokens"] == round(call["responseBytes"] / 4)


def test_rejected_arguments_logged_with_suggestion():
    with pytest.raises(Exception, match=r"unknown 'issueKey' \(did you mean 'issue_key'\?\)"):
        anyio.run(server.mcp.call_tool, "resolve_bug", {"issueKey": "OOP-1"})
    call = _rows("calls")[0]
    error = _rows("errors")[0]
    assert (call["tool"], call["status"]) == ("resolve_bug", "invalid_arguments")
    assert error["kind"] == "arg_error"
    assert error["unknown"] == ["issueKey"] and error["missingRequired"] == ["issue_key"]
    assert error["suggested"] == {"issueKey": "issue_key"}


def test_tool_call_logs_only_client_sent_arguments():
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value={"dryRun": True, "warnings": []}), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}):
        anyio.run(server.mcp.call_tool, "resolve_bug", {"issue_key": "OOP-1", "commit": "abc"})
    assert _details()[0]["arguments"] == {"issue_key": "OOP-1", "commit": "abc"}


def test_metrics_and_workflow_resources_are_gone():
    resources = anyio.run(server.mcp.list_resources)
    uris = {str(resource.uri) for resource in resources}
    assert "backlog://metrics" not in uris and "backlog://workflow-efficiency" not in uris
