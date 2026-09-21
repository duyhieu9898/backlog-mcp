import unittest
from datetime import date
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflows import story_task_overview


CONFIG = {
    "base_url": "https://example.backlog.com",
    "default_project_key": "AQM",
    "projects": ["AQM"],
    "users": {
        "me": {"id": 778617},
    },
}


PROJECT = {
    "key": "AQM",
    "id": 158425,
}


class StoryTaskOverviewTest(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.get_project_id.return_value = 158425
        mock.patch.object(story_task_overview, "BacklogClient", return_value=self.client).start()
        mock.patch.object(story_task_overview, "resolve_project", return_value=PROJECT).start()
        mock.patch.object(
            story_task_overview,
            "load_workflow_config",
            return_value={
                "issue_types": ["Story", "Task"],
                "excluded_statuses": ["Closed"],
                "assignee": "me",
                "fields": [
                    "issueKey",
                    "summary",
                    "description",
                    "status",
                    "dueDate",
                    "daysUntilDue",
                    "dueAlertLevel",
                ],
            },
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_my_story_task_overview_filters_and_returns_required_fields(self):
        self.client.get_issues.return_value = [
            {
                "issueType": {"name": "Story"},
                "status": {"name": "Open"},
                "assignee": {"id": 778617},
                "issueKey": "AQM-1",
                "summary": "Story A",
                "description": "Story desc",
                "dueDate": "2026-06-04",
            },
            {
                "issueType": {"name": "Task"},
                "status": {"name": "In Progress"},
                "assignee": {"id": 778617},
                "issueKey": "AQM-2",
                "summary": "Task A",
                "description": "Task desc",
                "dueDate": None,
            },
            {
                "issueType": {"name": "Task"},
                "status": {"name": "Closed"},
                "assignee": {"id": 778617},
                "summary": "Closed task",
            },
            {
                "issueType": {"name": "Task"},
                "status": {"name": "Open"},
                "assignee": {"id": 1001},
                "summary": "Other assignee",
            },
            {
                "issueType": {"name": "Bug"},
                "status": {"name": "Open"},
                "assignee": {"id": 778617},
                "summary": "Bug A",
            },
        ]

        result = story_task_overview.my_story_task_overview(CONFIG, project_key="AQM", today=date(2026, 6, 2))

        self.assertEqual(
            [
                {
                    "issueKey": "AQM-1",
                    "summary": "Story A",
                    "description": "Story desc",
                    "status": "Open",
                    "dueDate": "2026-06-04",
                    "daysUntilDue": 2,
                    "dueAlertLevel": None,
                },
                {
                    "issueKey": "AQM-2",
                    "summary": "Task A",
                    "description": "Task desc",
                    "status": "In Progress",
                    "dueDate": None,
                    "daysUntilDue": None,
                    "dueAlertLevel": None,
                },
            ],
            result,
        )

    def test_due_alert_levels(self):
        self.assertEqual(
            {"daysUntilDue": None, "dueAlertLevel": None},
            story_task_overview.due_status(None, date(2026, 6, 2)),
        )
        self.assertEqual(
            {"daysUntilDue": -1, "dueAlertLevel": 1},
            story_task_overview.due_status(date(2026, 6, 1), date(2026, 6, 2)),
        )
        self.assertEqual(
            {"daysUntilDue": 0, "dueAlertLevel": 2},
            story_task_overview.due_status(date(2026, 6, 2), date(2026, 6, 2)),
        )
        self.assertEqual(
            {"daysUntilDue": 1, "dueAlertLevel": 2},
            story_task_overview.due_status(date(2026, 6, 3), date(2026, 6, 2)),
        )
        self.assertEqual(
            {"daysUntilDue": 2, "dueAlertLevel": None},
            story_task_overview.due_status(date(2026, 6, 4), date(2026, 6, 2)),
        )


if __name__ == "__main__":
    unittest.main()
