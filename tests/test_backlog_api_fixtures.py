import json
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool.resolver import resolve_status
from workflows.bug_template import bug_context
from workflows.resolve_bug import issue_custom_field, my_open_bugs
from workflows.story_task_overview import my_story_task_overview


FIXTURES = ROOT / "tests" / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


CONFIG = {
    "base_url": "https://example.backlog.com",
    "default_project_key": "AQM",
    "projects": ["AQM", "OOP"],
    "users": {
        "me": {"id": 778617},
    },
}


def project_from_fixtures(project_key):
    return {
        "key": project_key,
        "id": 158425 if project_key == "AQM" else 82531,
        "bug": {
            "status_options": load_fixture(f"{project_key}_statuses.json"),
            "custom_fields": load_fixture(f"{project_key}_custom_fields.json"),
        },
    }


class BacklogApiFixtureTest(unittest.TestCase):
    def test_real_status_fixtures_resolve_workflow_status_labels(self):
        for project_key in ["AQM", "OOP"]:
            with self.subTest(project=project_key):
                project = project_from_fixtures(project_key)

                self.assertIsInstance(resolve_status(project, "Closed"), int)
                self.assertIsInstance(resolve_status(project, "Resolved"), int)

    def test_real_bug_issue_context_handles_backlog_issue_shape(self):
        issue = load_fixture("AQM_issue_bug.json")

        context = bug_context(issue)

        self.assertEqual(issue["issueKey"], context["issueKey"])
        self.assertEqual("Bug", issue["issueType"]["name"])
        self.assertEqual(issue["status"]["name"], context["status"])
        self.assertIn("rawDescription", context)
        self.assertIn("missingSections", context["descriptionMeta"])
        self.assertIn("Show popup", context["description"]["actual"])
        self.assertIn("Run history detail", context["description"]["expected"])
        self.assertIn("sharepoint", context["description"]["evidence"])

    def test_real_custom_field_shapes_are_detected_as_existing_values(self):
        issue = load_fixture("OOP_issue_bug.json")
        project = project_from_fixtures("OOP")

        qc_activity = issue_custom_field(issue, project, "qc_activity")
        corrective_action = issue_custom_field(issue, project, "corrective_action")

        self.assertIsNotNone(qc_activity)
        self.assertIsNotNone(qc_activity.get("value"))
        self.assertIsNotNone(corrective_action)

    def test_real_created_ut_bug_fixture_matches_business_rules(self):
        issue = load_fixture("AQM_issue_ut_bug_created.json")
        fields = {field["name"]: field.get("value") for field in issue["customFields"]}

        self.assertEqual("Bug", issue["issueType"]["name"])
        self.assertEqual("Closed", issue["status"]["name"])
        self.assertEqual(issue["createdUser"]["id"], issue["assignee"]["id"])
        self.assertEqual(1, issue["estimatedHours"])
        self.assertEqual(1, issue["actualHours"])
        self.assertEqual("Unit Test", fields["QC Activity"]["name"])
        self.assertEqual("Developer", fields["Detected Role"][0]["name"])
        self.assertEqual("fixed ut automation validation", fields["Corrective Action"])

    def test_real_resolved_bug_fixture_matches_business_rules(self):
        issue = load_fixture("AQM_issue_bug_resolved.json")
        fields = {field["name"]: field.get("value") for field in issue["customFields"]}

        self.assertEqual("Bug", issue["issueType"]["name"])
        self.assertEqual("Resolved", issue["status"]["name"])
        self.assertEqual(issue["createdUser"]["id"], issue["assignee"]["id"])
        self.assertEqual("Tester", fields["Detected Role"][0]["name"])
        self.assertEqual("no", fields["Impacted"])
        self.assertEqual(
            "fixed chuyển hướng đến run history detail sau khi run thành công",
            fields["Corrective Action"],
        )

    def test_real_issue_list_filters_open_bugs_assigned_to_me(self):
        issues = load_fixture("AQM_issues_assigned_me.json")
        project = project_from_fixtures("AQM")
        client = mock.Mock()
        client.get_project_id.return_value = project["id"]
        client.get_issues.return_value = issues

        with mock.patch("workflows.resolve_bug.BacklogClient", return_value=client), mock.patch(
            "workflows.resolve_bug.resolve_project",
            return_value=project,
        ), mock.patch(
            "workflows.resolve_bug.load_workflow_config",
            return_value={
                "issue_type": "Bug",
                "excluded_statuses": ["Closed"],
                "assignee": "me",
            },
        ):
            result = my_open_bugs(CONFIG, project_key="AQM")

        self.assertGreaterEqual(len(result), 1)
        self.assertTrue(all(item["status"] != "Closed" for item in result))

    def test_real_issue_list_filters_story_task_overview(self):
        issues = load_fixture("OOP_issues_assigned_me.json")
        project = project_from_fixtures("OOP")
        client = mock.Mock()
        client.get_project_id.return_value = project["id"]
        client.get_issues.return_value = issues

        with mock.patch("workflows.story_task_overview.BacklogClient", return_value=client), mock.patch(
            "workflows.story_task_overview.resolve_project",
            return_value=project,
        ), mock.patch(
            "workflows.story_task_overview.load_workflow_config",
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
        ):
            result = my_story_task_overview(CONFIG, project_key="OOP")

        self.assertTrue(
            all(
                set(item.keys())
                == {
                    "issueKey",
                    "summary",
                    "description",
                    "status",
                    "dueDate",
                    "daysUntilDue",
                    "dueAlertLevel",
                }
                for item in result
            )
        )


if __name__ == "__main__":
    unittest.main()
