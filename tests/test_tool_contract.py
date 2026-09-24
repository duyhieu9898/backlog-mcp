"""Contract for the MCP tool surface the models see (spec §9.1, §9.2, §9.4)."""

import anyio

from backlog_mcp import server

EXPECTED_TOOLS = {
    "get_issue", "get_issues", "create_issue", "update_issue", "get_my_open_bugs", "get_bug_context",
    "resolve_bug", "create_ut_bug", "get_bug_rules", "get_bug_fields", "get_my_work_overview", "get_my_project_status",
}
TOOLS = {tool.name: tool for tool in anyio.run(server.mcp.list_tools)}


def test_exactly_twelve_tools():
    assert set(TOOLS) == EXPECTED_TOOLS


def test_no_prompts_and_only_issue_resource_template():
    assert anyio.run(server.mcp.list_prompts) == []
    assert anyio.run(server.mcp.list_resources) == []
    templates = anyio.run(server.mcp.list_resource_templates)
    assert [t.uriTemplate for t in templates] == ["backlog://issue/{issue_key}"]
