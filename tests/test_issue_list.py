from datetime import date
from unittest import mock

from backlog_tool import issue_service, presenter


def test_due_alert_levels():
    today = date(2026, 6, 2)
    assert presenter.due_status(None, today) == {"daysUntilDue": None, "dueAlertLevel": None}
    assert presenter.due_status(date(2026, 6, 1), today) == {"daysUntilDue": -1, "dueAlertLevel": 1}
    assert presenter.due_status(date(2026, 6, 2), today) == {"daysUntilDue": 0, "dueAlertLevel": 2}
    assert presenter.due_status(date(2026, 6, 3), today) == {"daysUntilDue": 1, "dueAlertLevel": 2}
    assert presenter.due_status(date(2026, 6, 4), today) == {"daysUntilDue": 2, "dueAlertLevel": None}


def test_list_item_drops_description_and_adds_due_fields():
    issue = {
        "issueKey": "AQM-1", "summary": "Story A", "description": "long text",
        "issueType": {"name": "Story"}, "status": {"name": "Open"}, "dueDate": "2026-06-01T00:00:00Z",
        "assignee": {"id": 1, "name": "Me"}, "customFields": [{"name": "QC Activity", "value": {"name": "UT"}}],
    }
    item = presenter.list_item(issue, base_url="https://x", today=date(2026, 6, 2))
    # A personal list: the assignee is always the caller, resolve fields belong to resolve_bug.
    for dropped in ("description", "assignee", "customFields", "resourceUri"):
        assert dropped not in item
    assert item["url"] == "https://x/view/AQM-1"
    assert item["issueType"] == "Story" and item["status"] == "Open"
    assert item["daysUntilDue"] == -1 and item["dueAlertLevel"] == 1


def test_list_item_without_due_date_has_no_due_fields():
    item = presenter.list_item({"issueKey": "AQM-2", "summary": "Bug", "issueType": {"name": "Bug"}})
    assert "daysUntilDue" not in item and "dueAlertLevel" not in item


def test_list_summary_counts_types_and_deadlines():
    items = [
        {"issueType": "Bug", "dueAlertLevel": 1},
        {"issueType": "Bug"},
        {"issueType": "Task", "dueAlertLevel": 2},
    ]
    assert presenter.list_summary(items) == {"byType": {"Bug": 2, "Task": 1}, "overdueCount": 1, "dueSoonCount": 1}


def test_list_my_issues_filters_by_configured_user():
    config = {"users": {"me": {"id": 778617}}}
    with mock.patch.object(issue_service, "resolve_user_id", return_value=778617) as user, \
         mock.patch.object(issue_service, "get_issues", return_value=[]) as get:
        issue_service.list_my_issues(config, project_key="AQM", issue_types=["Bug"], limit=10)
    user.assert_called_once_with(config, "me")
    kwargs = get.call_args.kwargs
    assert kwargs["assignee_id"] == 778617
    assert kwargs["open_only"] is True
    assert kwargs["issue_types"] == ["Bug"]
    assert kwargs["limit"] == 10


def test_issue_type_names_match_case_insensitively():
    project = {"bug": {"issue_type_options": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Issue|Risk"}]}}
    assert issue_service._resolve_issue_type_ids(project, ["bug", "ISSUE|RISK"]) == [1, 2]


BEFORE = {
    "issueKey": "NLN-1", "summary": "Old", "description": "old text", "status": {"name": "Open"},
    "priority": {"name": "Normal"}, "assignee": {"id": 1, "name": "Dev"}, "dueDate": "2026-10-01T00:00:00Z",
    "customFields": [{"id": 5, "name": "QC Activity", "value": {"id": 1, "name": "Unit Test"}}],
}


def test_issue_changes_lists_only_changed_fields_by_name():
    after = {**BEFORE, "description": "new text", "status": {"name": "In Progress"}, "dueDate": "2026-10-02T00:00:00Z",
             "updated": "2026-09-28T10:00:00Z"}
    assert presenter.issue_changes(BEFORE, after, comment="note") == [
        {"field": "Status", "from": "Open", "to": "In Progress"},
        {"field": "Due Date", "from": "2026-10-01", "to": "2026-10-02"},
        {"field": "Description", "from": "old text", "to": "new text"},
        {"field": "Comment", "from": None, "to": "note"},
    ]


def test_issue_changes_includes_custom_fields_by_label():
    after = {**BEFORE, "customFields": [{"id": 5, "name": "QC Activity", "value": {"id": 2, "name": "Integration Test"}}]}
    assert presenter.issue_changes(BEFORE, after) == [
        {"field": "QC Activity", "from": "Unit Test", "to": "Integration Test"},
    ]


def test_issue_changes_for_a_new_issue_lists_every_set_field():
    changes = presenter.issue_changes(None, BEFORE)
    assert {"field": "Summary", "from": None, "to": "Old"} in changes
    assert {"field": "Assignee", "from": None, "to": "Dev"} in changes
    assert {"field": "QC Activity", "from": None, "to": "Unit Test"} in changes
