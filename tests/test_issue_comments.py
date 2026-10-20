import copy
import json
from pathlib import Path
from unittest import mock

from backlog_mcp import server
from backlog_tool import issue_service
from workflows.bug_template import handoff_comment, issue_context

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ME = "Hieu Nguyen Duy (DN.DEV)"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def comment(created, author, content, changes):
    return {
        "content": content,
        "created": created,
        "createdUser": {"name": author},
        "changeLog": [{"field": f, "originalValue": old, "newValue": new} for f, old, new in changes],
    }


def issue(assignee=ME):
    return {"issueKey": "OOP-1", "summary": "Bug", "status": {"name": "Open"}, "assignee": {"name": assignee}}


def test_qc_reopen_comment_is_the_handoff():
    context = issue_context(issue(), comments=load("OOP_issue_comments_reopened.json"))

    handoff = context["handoffComment"]
    assert handoff["author"] == "QA Reporter"
    assert "Transfer Failed" in handoff["content"]
    assert "status: Resolved -> Open" in handoff["changes"]
    assert context["commentCount"] == 2
    assert "comments" not in context


def test_teammate_handing_work_over_is_the_handoff():
    comments = [comment("2026-10-01T00:00:00Z", "BE Dev", "API xong rồi, nhờ FE nối màn hình", [("assigner", "BE Dev", ME)])]
    assert handoff_comment(comments, ME)["content"] == "API xong rồi, nhờ FE nối màn hình"


def test_latest_assignment_without_text_hides_an_older_handoff():
    comments = [
        comment("2026-10-01T00:00:00Z", "QA", "thiếu cột A", [("assigner", "QA", ME)]),
        comment("2026-10-02T00:00:00Z", ME, "", [("assigner", ME, "QA")]),
        comment("2026-10-03T00:00:00Z", "QA", "", [("assigner", "QA", ME)]),
    ]
    assert handoff_comment(comments, ME) is None


def test_issue_not_assigned_to_me_has_no_handoff():
    # A bug I resolved and handed to QC: my resolve comment is no request for me.
    context = issue_context(issue("QA Reporter"), comments=load("OOP_issue_comments_reopened.json"), handoff=False)
    assert "handoffComment" not in context
    assert context["commentCount"] == 2


def test_assigned_to_me_compares_with_the_api_key_owner():
    config = {"users": {"me": {"id": 778617}}}
    assert issue_service.assigned_to_me(config, {"assignee": {"id": 778617}})
    assert not issue_service.assigned_to_me(config, {"assignee": {"id": 315996}})
    assert not issue_service.assigned_to_me(config, {"assignee": None})


def test_no_comments_adds_only_the_count():
    context = issue_context(issue(), comments=[])
    assert context["commentCount"] == 0
    assert "handoffComment" not in context


def test_include_comments_lists_written_comments_oldest_first():
    context = issue_context(issue(), comments=load("OOP_issue_comments_reopened.json"), include_comments=True)
    assert [c["content"][:7] for c in context["comments"]] == ["Commit:", "Ở Partn"]


def test_long_comment_is_cut():
    comments = [comment("2026-10-01T00:00:00Z", "QA", "x" * 5000, [("assigner", "QA", ME)])]
    assert len(handoff_comment(comments, ME)["content"]) == 2001


def test_get_issue_tool_reads_comments_only_where_needed():
    raw = copy.deepcopy(issue())
    comments = load("OOP_issue_comments_reopened.json")
    with mock.patch("backlog_mcp.server.get_config_instance", return_value={"base_url": "https://x", "projects": ["OOP"]}), \
         mock.patch("backlog_mcp.server.issue_service.get_issue", return_value=raw), \
         mock.patch("backlog_mcp.server.issue_service.get_comments", return_value=comments) as get_comments, \
         mock.patch("backlog_mcp.server.issue_service.assigned_to_me", return_value=True):
        compact = server.get_issue("OOP-1").structuredContent
        server.get_issue("OOP-1", view="full")
        assert get_comments.call_count == 1
        full = server.get_issue("OOP-1", view="full", include_comments=True).structuredContent

    assert "Transfer Failed" in json.dumps(compact, ensure_ascii=False)
    assert "Transfer Failed" in json.dumps(full, ensure_ascii=False)
