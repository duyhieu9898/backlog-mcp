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
    }
    item = presenter.list_item(issue, today=date(2026, 6, 2))
    assert "description" not in item
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
