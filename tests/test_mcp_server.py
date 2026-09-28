import json
import os
from unittest import mock

import anyio
import pytest

from backlog_mcp import server
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


def test_list_my_issues_tool_maps_pagination_sort_and_field_selection():
    with mock.patch("backlog_mcp.server.issue_service.list_my_issues", return_value=[]) as get_mock:
        result = server.list_my_issues(
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


def test_list_my_issues_tool_with_invalid_cursor_returns_error():
    result = server.list_my_issues(cursor="invalid")
    assert result.isError is True
    assert "Invalid cursor format" in result.content[0].text


def test_build_result_returns_stable_success_envelope_with_pagination():
    from backlog_tool import telemetry

    data = [{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}]
    telemetry.start_call("list_my_issues", {})
    result = server._build_result(
        data,
        tool="list_my_issues",
        list_key="issues",
        limit=1,
        offset=0,
        paginated=True,
    )

    assert result.isError is False
    assert result.structuredContent == {
        "ok": True,
        "data": {"issues": [{"issueKey": "AQM-1", "summary": "Fix it", "status": "Open"}], "count": 1},
        "pagination": {
            "limit": 1,
            "nextCursor": "1",
            "hasMore": True,
        },
    }
    assert result.meta["tool"] == "list_my_issues"
    assert result.meta["command"] == "list_my_issues"
    assert result.meta["resourceUris"] == ["backlog://issue/AQM-1"]
    assert result.meta["traceId"]
    assert json.loads(result.content[0].text) == result.structuredContent


def test_server_uses_claude_project_directory_as_workspace():
    with (
        mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/work/AQM"}, clear=True),
        mock.patch("backlog_mcp.server.issue_service.list_my_issues", return_value=[]) as get_mock,
    ):
        server.list_my_issues(project_key="AQM")

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
    list_my_issues = tools["list_my_issues"]
    get_issue = tools["get_issue"]
    update_issue = tools["update_issue"]
    resolve_bug = tools["resolve_bug"]
    create_issue = tools["create_issue"]

    assert "Use when" in list_my_issues.description
    assert "Do not use" in list_my_issues.description
    assert "view" not in list_my_issues.inputSchema["properties"]
    assert get_issue.inputSchema["properties"]["view"]["enum"] == ["compact", "full"]
    assert "issue_key" in get_issue.inputSchema["properties"]
    assert "issue_id" not in get_issue.inputSchema["properties"]
    assert "issueKey" not in get_issue.inputSchema["properties"]
    assert "issue_key" in update_issue.inputSchema["properties"]
    assert "issue_id" not in update_issue.inputSchema["properties"]
    assert "issue_key" in resolve_bug.inputSchema["properties"]
    assert "issueKey" not in resolve_bug.inputSchema["properties"]
    assert "cursor" in list_my_issues.inputSchema["properties"]
    assert "offset" not in list_my_issues.inputSchema["properties"]
    assert list_my_issues.inputSchema["properties"]["cursor"]["type"] == "string"
    for mutation_name in ("create_issue", "update_issue", "resolve_bug", "create_ut_bug"):
        mode_schema = tools[mutation_name].inputSchema["properties"]["mode"]
        assert mode_schema["enum"] == ["preview", "apply"]
        assert mode_schema["default"] == "preview"
    assert "workspace_path" not in create_issue.inputSchema["properties"]
    assert "parent" not in create_issue.inputSchema["properties"]
    assert "parent_key" in create_issue.inputSchema["properties"]
    assert create_issue.inputSchema["properties"]["project_key"]["default"] == ""
    assert "issue_type" in create_issue.inputSchema.get("required", [])



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
    assert tools["get_issue"].inputSchema["additionalProperties"] is False
    assert tools["get_issue"].inputSchema["additionalProperties"] is False

def test_resources_have_json_mime_type_and_issue_template():
    async def load_resources():
        return await server.mcp.list_resources(), await server.mcp.list_resource_templates()

    resources, templates = anyio.run(load_resources)
    resource_by_uri = {str(resource.uri): resource for resource in resources}
    template_by_uri = {template.uriTemplate: template for template in templates}

    assert "backlog://config" not in resource_by_uri
    assert template_by_uri["backlog://issue/{issue_key}"].mimeType == "application/json"
    assert template_by_uri["backlog://issue/{issue_key}"].meta == {"kind": "issue", "scope": "project"}


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
            summary="fails",
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


def test_personal_routing_contract_is_explicit_and_domain_first():
    async def load_tools():
        return await server.mcp.list_tools()

    tools = {tool.name: tool for tool in anyio.run(load_tools)}

    assert "Backlog is explicitly invoked" in tools["list_my_issues"].description
    assert "not a PM/team/project-health dashboard" in tools["list_my_issues"].description
    assert "no get_issue, get_bug_rules or get_bug_fields call is needed first" in tools["resolve_bug"].description
    assert "get_issue returns it" in tools["list_my_issues"].description
    assert "parsed" in tools["get_issue"].description and "attachments" in tools["get_issue"].description


def test_server_instructions_require_backlog_activation_and_minimal_bug_paths():
    instructions = server.SERVER_INSTRUCTIONS
    assert "Activation:" in instructions and "without that signal" in instructions
    assert 'resolve_bug(mode="apply"), one call, no lookups first' in instructions
    assert "-> get_issue" in instructions and "lists attachments" in instructions
    assert 'Writes (resolve_bug, create_issue, update_issue, create_ut_bug): call with mode="apply" directly' in instructions
    assert "report the returned changes and every warning" in instructions
    assert "preview -> apply" not in instructions


def test_server_instructions_name_only_existing_tools():
    import re

    tools = {tool.name for tool in anyio.run(server.mcp.list_tools)}
    named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", server.SERVER_INSTRUCTIONS)) - {"issue_types"}
    assert named <= tools, named - tools




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
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value={"issueKey": "OOP-1"}):
        ok = server.get_issue("OOP-1")
    with mock.patch("backlog_mcp.server.issue_service.get_issue", side_effect=ValueError("Boom")):
        bad = server.get_issue("OOP-1")

    first, second = _rows("calls")
    assert (first["tool"], first["status"], first["projectKey"]) == ("get_issue", "ok", "OOP")
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


def test_resolve_bug_apply_response_shape():
    built = {
        "dryRun": False, "issue": "OOP-1", "project": "OOP", "payload": {}, "context": {},
        "assignment": {}, "warnings": ["Detected Role is Developer, not Tester; confirm the reporter is the intended QC assignee."],
        "changes": [{"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"}],
        "updated": {"issueKey": "OOP-1", "status": {"name": "Resolved"}, "assignee": {"id": 2, "name": "QC"}},
    }
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value=built), \
         mock.patch("backlog_mcp.server.project_keys", return_value=["OOP"]), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}), \
         mock.patch("backlog_mcp.server.view_base_url", return_value="https://x.backlog.com"):
        result = server.resolve_bug("OOP-1", mode="apply")
    assert result.structuredContent["data"] == {
        "issue": "OOP-1", "status": "Resolved", "assignee": "QC", "url": "https://x.backlog.com/view/OOP-1",
        "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": built["warnings"],
    }
    assert "Tester" in result.content[0].text


def test_resolve_bug_preview_response_shape():
    built = {"dryRun": True, "issue": "OOP-1", "project": "OOP", "assignment": {"from": {}, "to": {}},
             "changes": [{"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"}], "warnings": []}
    with mock.patch("backlog_mcp.server.bug_workflow.resolve_bug", return_value=built), \
         mock.patch("backlog_mcp.server.project_keys", return_value=["OOP"]), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}):
        result = server.resolve_bug("OOP-1")
    assert result.structuredContent["data"] == {
        "dryRun": True, "issue": "OOP-1", "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": [],
    }


def test_resolve_bug_description_says_apply_once():
    tools = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}
    description = tools["resolve_bug"].description
    assert 'One call with mode="apply" does the whole resolution' in description
    assert "no get_issue, get_bug_rules or get_bug_fields call is needed first" in description
    assert "Required in apply mode" not in tools["resolve_bug"].inputSchema["properties"]["fix_description"]["description"]


def test_list_my_issues_tool_items_omit_description_and_summarize():
    raw = [
        {"issueKey": "OOP-1", "summary": "Lỗi", "description": "long text " * 50, "issueType": {"name": "Bug"},
         "status": {"name": "Open"}, "customFields": [{"name": "Severity", "value": {"name": "High"}}]},
        {"issueKey": "OOP-2", "summary": "Việc", "issueType": {"name": "Task"}, "status": {"name": "Open"}},
    ]
    with mock.patch("backlog_mcp.server.issue_service.list_my_issues", return_value=raw), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={}), \
         mock.patch("backlog_mcp.server.view_base_url", return_value=""):
        result = server.list_my_issues()
    data = result.structuredContent["data"]
    bug, task = data["issues"]
    assert "description" not in bug
    assert bug["issueKey"] == "OOP-1" and bug["issueType"] == "Bug" and bug["status"] == "Open"
    assert "customFields" not in bug
    assert data["count"] == 2
    assert data["summary"] == {"byType": {"Bug": 1, "Task": 1}, "overdueCount": 0, "dueSoonCount": 0}
    assert result.structuredContent["pagination"]["hasMore"] is False


def test_create_issue_blank_parent_key_means_no_parent():
    with mock.patch("backlog_mcp.server.issue_service.create_issue", return_value={"dryRun": True}) as create:
        result = server.create_issue("Title", "Task", parent_key="   ")
    assert result.isError is False
    assert create.call_args.kwargs["parent_key"] == ""


def test_bug_support_tools_accept_lowercase_project_key():
    with mock.patch("backlog_mcp.server.guidance.resolve_rules", return_value={"ok": True}) as rules:
        result = server.get_bug_rules(project_key="oop", issue_key="OOP-12760")
    assert result.isError is False and rules.call_args.args[1] == "OOP"


def test_issue_resource_normalizes_key_and_rejects_bad_key():
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value={"issueKey": "AQM-1"}) as get:
        server.issue_resource(" aqm-1 ")
    assert get.call_args.args[1] == "AQM-1"
    with mock.patch("backlog_mcp.server.issue_service.get_issue") as get:
        res = json.loads(server.issue_resource("not a key"))
    assert res["ok"] is False and "OOP-123" in res["error"]
    get.assert_not_called()


def test_error_telemetry_keeps_project_for_lowercase_key():
    with mock.patch("backlog_mcp.server.issue_service.get_issue", side_effect=ValueError("Boom")):
        server.get_issue(" oop-1 ")
    assert _rows("calls")[0]["projectKey"] == "OOP"


def test_applied_update_reports_previous_values():
    before = {"issueKey": "NLN-1", "description": "old", "status": {"name": "Open"}}
    after = {"issueKey": "NLN-1", "description": "new", "status": {"name": "Open"}}
    with mock.patch("backlog_mcp.server.issue_service.get_issue", return_value=before), \
         mock.patch("backlog_mcp.server.issue_service.update_issue", return_value=after), \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={"base_url": "https://x", "projects": ["NLN"]}):
        result = server.update_issue("NLN-1", description="new", comment="why", mode="apply")
    assert result.structuredContent["data"] == {
        "issueKey": "NLN-1",
        "url": "https://x/view/NLN-1",
        "changes": [
            {"field": "Description", "from": "old", "to": "new"},
            {"field": "Comment", "from": None, "to": "why"},
        ],
    }


def test_update_preview_does_not_read_the_issue():
    with mock.patch("backlog_mcp.server.issue_service.get_issue") as get, \
         mock.patch("backlog_mcp.server.issue_service.update_issue", return_value={"dryRun": True}):
        server.update_issue("NLN-1", summary="x")
    get.assert_not_called()


def test_applied_ut_bug_reports_the_closed_issue():
    updated = {"issueKey": "NLN-9", "summary": "[NLN-1][m] fails", "status": {"name": "Closed"}}
    with mock.patch("backlog_mcp.server.ut_bug.create_subtask_bug", return_value={"issueKey": "NLN-9", "updated": updated}) as create, \
         mock.patch("backlog_mcp.server.get_config_instance", return_value={"base_url": "https://x", "projects": ["NLN"]}):
        result = server.create_ut_bug("NLN-1", "m", "fails", mode="apply")
    assert create.call_args.kwargs["summary"] == "fails"
    data = result.structuredContent["data"]
    assert data["issueKey"] == "NLN-9"
    assert {"field": "Status", "from": None, "to": "Closed"} in data["changes"]


def test_tools_declare_read_and_write_annotations():
    tools = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}
    for name in ("get_issue", "list_my_issues", "get_bug_rules", "get_bug_fields"):
        assert tools[name].annotations.readOnlyHint is True, name
    for name in ("create_issue", "create_ut_bug", "update_issue", "resolve_bug"):
        assert tools[name].annotations.readOnlyHint is False, name
        assert tools[name].annotations.idempotentHint is False, name
    assert tools["update_issue"].annotations.destructiveHint is True
    assert tools["create_issue"].annotations.destructiveHint is False
