from unittest import mock

from workflows import personal_status


def test_get_my_project_status_aggregates_personal_work():
    config = {"base_url": "https://example.backlog.com"}
    stories = [
        {"issueKey": "OOP-1", "daysUntilDue": -1, "dueAlertLevel": 1},
        {"issueKey": "OOP-2", "daysUntilDue": 1, "dueAlertLevel": 2},
    ]
    bugs = [
        {
            "id": 10,
            "issueKey": "OOP-3",
            "summary": "Broken delete",
            "status": {"name": "Open"},
        }
    ]

    with mock.patch.object(
        personal_status.story_task_overview,
        "my_story_task_overview",
        return_value=stories,
    ), mock.patch.object(
        personal_status.bug_workflow,
        "my_open_bugs_raw",
        return_value=bugs,
    ), mock.patch.object(
        personal_status.presenter,
        "compact_issue",
        return_value={"issueKey": "OOP-3", "summary": "Broken delete", "status": "Open"},
    ):
        result = personal_status.get_my_project_status(
            config,
            project_key="OOP",
            start_path="/work/OOP",
        )

    assert result["storiesAndTasks"] == stories
    assert result["openBugs"][0]["issueKey"] == "OOP-3"
    assert result["summary"] == {
        "storyTaskCount": 2,
        "openBugCount": 1,
        "overdueCount": 1,
        "dueSoonCount": 1,
    }
