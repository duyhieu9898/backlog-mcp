"""Contract for the MCP tool surface the models see (spec §9.1, §9.2, §9.4)."""

import json
import re
from datetime import date
from unittest import mock

import anyio
import pytest

from backlog_mcp import server
from backlog_mcp.results import _build_result

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


ISSUE_KEY_PARAMS = {"issue_key", "parent_key"}


def _params(tool):
    return tool.inputSchema.get("properties", {})


def test_parameters_are_snake_case_and_forbid_extras():
    for name, tool in TOOLS.items():
        assert tool.inputSchema.get("additionalProperties") is False, name
        for param in _params(tool):
            assert re.fullmatch(r"[a-z][a-z0-9_]*", param), (name, param)


def test_issue_parameters_use_canonical_names_with_example():
    for name, tool in TOOLS.items():
        params = _params(tool)
        assert not {"issue_ref", "issue_id", "issueKey"} & set(params), name
        for param in ISSUE_KEY_PARAMS & set(params):
            assert "OOP-123" in params[param]["description"], (name, param)
    assert "issue_key" in _params(TOOLS["get_issue"]) and "issue_key" in _params(TOOLS["update_issue"])


def test_fixed_value_parameters_are_enums():
    for name, tool in TOOLS.items():
        for param in ("mode", "order", "view"):
            if param in _params(tool):
                schema = _params(tool)[param]
                options = schema.get("enum") or [e for s in schema.get("anyOf", []) for e in s.get("enum", [])]
                assert options, (name, param)


def test_every_description_says_use_when():
    for name, tool in TOOLS.items():
        assert "Use when" in tool.description, name


@pytest.mark.parametrize("raw, expected", [(" oop-912762 ", "OOP-912762"), ("OOP-1", "OOP-1")])
def test_issue_key_is_normalized(raw, expected):
    with mock.patch.object(server, "get_config_instance", return_value={}), \
         mock.patch.object(server, "project_keys", return_value=["OOP", "AQM"]):
        assert server._issue_key(raw) == expected


def test_issue_key_rejects_bad_format_and_unknown_project():
    with mock.patch.object(server, "get_config_instance", return_value={}), \
         mock.patch.object(server, "project_keys", return_value=["OOP", "AQM"]):
        with pytest.raises(ValueError, match="OOP-123"):
            server._issue_key("12345")
        assert server._issue_key("12345", allow_numeric=True) == "12345"
        with pytest.raises(ValueError, match="Configured projects: OOP, AQM"):
            server._issue_key("ZZZ-1")


def test_resolve_bug_rejects_unconfigured_prefix_without_backend_call():
    with mock.patch.object(server, "get_config_instance", return_value={}), \
         mock.patch.object(server, "project_keys", return_value=["OOP"]), \
         mock.patch.object(server.bug_workflow, "resolve_bug") as resolve:
        result = server.resolve_bug("ZZZ-1", mode="apply")
    assert result.isError and "Configured projects: OOP" in result.content[0].text
    resolve.assert_not_called()


@pytest.mark.parametrize("data, kwargs", [
    ([], {"list_key": "bugs", "paginated": True, "limit": 50}),
    ([{"issueKey": "OOP-1", "summary": "Lỗi đăng nhập", "startDate": date(2026, 9, 24)}], {"list_key": "bugs", "paginated": True, "limit": 50}),
    ({"dryRun": True, "issue": "OOP-1", "changes": [{"field": "Status", "from": "Open", "to": "Resolved"}], "warnings": ["w"]}, {}),
    ({}, {}),
])
def test_text_is_full_json_of_structured_content(data, kwargs):
    result = _build_result(data, "get_my_open_bugs", **kwargs)
    text = result.content[0].text
    assert json.loads(text) == json.loads(json.dumps(result.structuredContent, default=str))
    assert "(structured data)" not in text and "No data." not in text
    assert ", " not in text[:40]


def test_list_results_state_count():
    empty = _build_result([], "get_my_open_bugs", list_key="bugs", paginated=True, limit=50)
    assert empty.structuredContent["data"] == {"bugs": [], "count": 0}
    assert '"count":0' in empty.content[0].text


def test_vietnamese_text_is_not_escaped():
    result = _build_result({"summary": "Lỗi đăng nhập"}, "get_issue")
    assert "Lỗi đăng nhập" in result.content[0].text
