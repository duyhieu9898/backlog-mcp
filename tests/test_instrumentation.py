"""Canaries for the FastMCP internals that backlog_mcp.instrumentation patches."""

import anyio
import pytest

from backlog_mcp import server


def test_generated_schemas_forbid_extra_properties():
    tools = anyio.run(server.mcp.list_tools)
    assert tools
    for tool in tools:
        assert tool.inputSchema.get("additionalProperties") is False, tool.name


def test_every_tool_has_title_and_destructive_hint():
    for tool in anyio.run(server.mcp.list_tools):
        assert tool.annotations and tool.annotations.title, tool.name
        assert tool.annotations.destructiveHint is not None, tool.name


def test_unknown_argument_is_rejected_before_the_tool_runs():
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        anyio.run(server.mcp.call_tool, "get_issue", {"issue_key": "OOP-1", "bogus": 1})
