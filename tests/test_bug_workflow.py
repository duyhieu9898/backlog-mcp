import unittest
from datetime import date
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from workflows import resolve_bug as bug_workflow
from workflows.bug_template import bug_context, bug_description_metadata, parse_bug_description


CONFIG = {
    "base_url": "https://example.backlog.com",
    "default_project_key": "AQM",
    "projects": ["AQM"],
    "users": {
        "me": {"id": 778617},
    },
    "defaults": {
        "assignee": "me",
    },
}


PROJECT = {
    "key": "AQM",
    "id": 158425,
    "bug": {
        "issue_type_options": [
            {"id": 1, "name": "Bug"},
        ],
        "status_options": [
            {"id": 4, "name": "Resolved"},
        ],
        "custom_fields": {
            "qc_activity": {
                "field": "customField_1",
                "value_options": [{"id": 10, "name": "Integration Test"}],
            },
            "cause_category": {
                "field": "customField_2",
                "value_options": [{"id": 20, "name": "Not Applicable"}],
            },
            "bug_origin": {
                "field": "customField_3",
                "value_options": [{"id": 30, "name": "FUN_Incomplete Function"}],
            },
            "impacted": {
                "field": "customField_4",
            },
            "corrective_action": {
                "field": "customField_5",
            },
            "resolution": {
                "field": "customField_6",
            },
            "detected_role": {
                "field": "customField_7",
            },
        },
    },
}


BUG_DESCRIPTION = """**Environment:
DEV

**Pre-Condition:
- Logged in

**Steps to reproduce:
1. Open page
2. Click save

**Actual:
Error appears

**Expected:
Save succeeds

 **Evidence:
screen.png
"""


BUG_ISSUE = {
    "issueKey": "AQM-123",
    "summary": "Save fails",
    "description": BUG_DESCRIPTION,
    "issueType": {"name": "Bug"},
    "status": {"name": "In Progress"},
    "assignee": {"id": 778617, "name": "Me"},
    "createdUser": {"id": 1001, "name": "Reporter"},
    "project": {"projectKey": "AQM"},
    "startDate": None,
    "dueDate": None,
    "estimatedHours": None,
    "actualHours": None,
}


class BugWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.get_project_id.return_value = 158425
        self.client.get_issue.return_value = BUG_ISSUE
        mock.patch.object(
            bug_workflow,
            "load_workflow_config",
            return_value={
                "issue_type": "Bug",
                "excluded_statuses": ["Closed"],
                "status": "Resolved",
                "assignee": "me",
                "estimated_hours": 1,
                "actual_hours": 1,
                "due_in_days": 2,
                "corrective_action": "fixed {description_lower}",
                "custom_fields": {
                    "qc_activity": "Integration Test",
                    "cause_category": "Not Applicable",
                    "bug_origin": "FUN_Incomplete Function",
                    "impacted": "no",
                    "resolution": "fixed",
                },
            },
        ).start()
        mock.patch.object(bug_workflow, "BacklogClient", return_value=self.client).start()
        mock.patch.object(bug_workflow, "resolve_project", return_value=PROJECT).start()
        mock.patch.object(bug_workflow, "log_event").start()
        self.addCleanup(mock.patch.stopall)

    def test_parse_bug_description_extracts_template_sections(self):
        parsed = parse_bug_description(BUG_DESCRIPTION)

        self.assertEqual("DEV", parsed["environment"])
        self.assertIn("Logged in", parsed["pre_condition"])
        self.assertIn("Click save", parsed["steps_to_reproduce"])
        self.assertEqual("Error appears", parsed["actual"])
        self.assertEqual("Save succeeds", parsed["expected"])
        self.assertEqual("screen.png", parsed["evidence"])

    def test_parse_bug_description_supports_closed_bold_markers(self):
        parsed = parse_bug_description("**Actual:**\nOld format\n\n**Expected:**\nStill supported")

        self.assertEqual("Old format", parsed["actual"])
        self.assertEqual("Still supported", parsed["expected"])

    def test_parse_bug_description_supports_standard_markers(self):
        parsed = parse_bug_description("**Actual**:\nStandard format\n\n**Expected**:\nStill supported")

        self.assertEqual("Standard format", parsed["actual"])
        self.assertEqual("Still supported", parsed["expected"])

    def test_parse_bug_description_supports_inline_marker_values(self):
        parsed = parse_bug_description("**Environment: Local**\n\n**Actual: Inline actual\n\n**Expected: Inline expected")

        self.assertEqual("Local", parsed["environment"])
        self.assertEqual("Inline actual", parsed["actual"])
        self.assertEqual("Inline expected", parsed["expected"])

    def test_bug_description_metadata_marks_missing_sections_for_ai_fallback(self):
        parsed = parse_bug_description("**Actual:\nOnly actual is present")
        meta = bug_description_metadata(parsed)

        self.assertTrue(meta["hasTemplateMarkers"])
        self.assertEqual(["actual"], meta["presentSections"])
        self.assertIn("expected", meta["missingSections"])
        self.assertIn("steps_to_reproduce", meta["missingSections"])

    def test_bug_context_includes_structured_description(self):
        context = bug_context(BUG_ISSUE)

        self.assertEqual("AQM-123", context["issueKey"])
        self.assertEqual("Save fails", context["summary"])
        self.assertEqual("In Progress", context["status"])
        self.assertEqual("Error appears", context["description"]["actual"])
        self.assertEqual([], context["descriptionMeta"]["missingSections"])
        self.assertEqual({"id": 1001, "name": "Reporter"}, context["createdUser"])

    def test_my_open_bugs_filters_bug_status_and_assignee(self):
        issues = [
            BUG_ISSUE,
            {**BUG_ISSUE, "issueKey": "AQM-124", "status": {"name": "Closed"}},
            {**BUG_ISSUE, "issueKey": "AQM-125", "issueType": {"name": "Task"}},
            {**BUG_ISSUE, "issueKey": "AQM-126", "assignee": {"id": 1002}},
        ]
        self.client.get_issues.return_value = issues

        result = bug_workflow.my_open_bugs(CONFIG, project_key="AQM")

        self.assertEqual(["AQM-123"], [item["issueKey"] for item in result])

    def test_resolve_bug_dry_run_builds_personal_update_payload(self):
        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            actual_hours=1.5,
            today=date(2026, 6, 2),
            comment="Fixed save issue",
        )

        payload = result["payload"]
        self.client.update_issue.assert_not_called()
        self.assertTrue(result["dryRun"])
        self.assertEqual(4, payload["statusId"])
        self.assertEqual(1001, payload["assigneeId"])
        self.assertEqual("2026-06-02", payload["startDate"])
        self.assertEqual("2026-06-04", payload["dueDate"])
        self.assertEqual(1, payload["estimatedHours"])
        self.assertEqual(1.5, payload["actualHours"])
        self.assertEqual("Fixed save issue", payload["comment"])
        self.assertEqual(10, payload["customField_1"])
        self.assertEqual(20, payload["customField_2"])
        self.assertEqual(30, payload["customField_3"])
        self.assertEqual("no", payload["customField_4"])
        self.assertEqual("fixed save fails", payload["customField_5"])
        self.assertEqual("fixed", payload["customField_6"])
        self.assertEqual(
            {
                "from": {"id": 778617, "name": "Me"},
                "to": {"id": 1001, "name": "Reporter"},
                "source": "createdUser (reporter)",
            },
            result["assignment"],
        )
        status_change = next(change for change in result["changes"] if change["key"] == "statusId")
        self.assertEqual("In Progress", status_change["from"])
        self.assertEqual("Resolved", status_change["value"])
        assignee_change = next(change for change in result["changes"] if change["key"] == "assigneeId")
        self.assertEqual({"id": 778617, "name": "Me"}, assignee_change["from"])
        self.assertEqual({"id": 1001, "name": "Reporter"}, assignee_change["value"])
        self.assertEqual("createdUser (reporter)", assignee_change["source"])

    def test_resolve_bug_uses_fix_description_for_corrective_action(self):
        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            fix_description="Validated save button",
        )

        self.assertEqual("fixed validated save button", result["payload"]["customField_5"])

    def test_resolve_bug_appends_commit_to_comment(self):
        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            comment="Ready for QC.",
            commit="30e0ca6",
        )

        self.assertEqual("Ready for QC. Commit: 30e0ca6.", result["payload"]["comment"])

    def test_resolve_bug_creates_comment_from_commit(self):
        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            commit="30e0ca6",
        )

        self.assertEqual("Commit: 30e0ca6.", result["payload"]["comment"])

    def test_resolve_bug_calculates_missing_due_date_from_existing_start_date(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "startDate": "2026-05-20T00:00:00Z",
        }

        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
        )

        self.assertNotIn("startDate", result["payload"])
        self.assertEqual("2026-05-22", result["payload"]["dueDate"])

    def test_resolve_bug_rejects_excluded_status(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "status": {"name": "Closed"},
        }

        with self.assertRaisesRegex(ValueError, "excluded status 'Closed'"):
            bug_workflow.resolve_bug(
                CONFIG,
                "AQM-123",
                dry_run=True,
                today=date(2026, 6, 2),
            )

    def test_resolve_bug_rejects_issue_assigned_to_another_user(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "assignee": {"id": 1002, "name": "Another Developer"},
        }

        with self.assertRaisesRegex(ValueError, "not assigned to the configured resolve user"):
            bug_workflow.resolve_bug(
                CONFIG,
                "AQM-123",
                dry_run=True,
                today=date(2026, 6, 2),
            )

    def test_corrective_action_strips_summary_prefix_when_no_fix_description(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "summary": "[BUG][AQM-74][Chatbox] - Layout broken",
        }

        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))

        self.assertEqual("fixed layout broken", result["payload"]["customField_5"])

    def test_resolve_dry_run_includes_changes_and_warnings(self):
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))

        change_keys = {change["key"] for change in result["changes"]}
        self.assertIn("statusId", change_keys)
        self.assertIn("customField_5", change_keys)  # corrective_action
        self.assertTrue(any("fix-description" in w for w in result["warnings"]))

    def test_resolve_no_warning_when_fix_description_given(self):
        result = bug_workflow.resolve_bug(
            CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="Fixed it"
        )

        self.assertEqual([], result["warnings"])

    def test_resolve_warns_when_detected_role_is_not_tester(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "customFields": [
                {"id": 7, "name": "Detected Role", "value": [{"id": 1, "name": "Developer"}]},
            ],
        }

        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            fix_description="Fixed it",
        )

        self.assertTrue(any("not Tester" in warning for warning in result["warnings"]))

    def test_resolve_bug_only_sets_missing_defaults(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "startDate": "2026-06-01",
            "dueDate": "2026-06-03",
            "estimatedHours": 2,
            "actualHours": 3,
            "customFields": [
                {"id": 1, "name": "QC Activity", "value": {"id": 99, "name": "Unit Test"}},
                {"id": 2, "name": "Cause Category", "value": {"id": 98, "name": "Existing"}},
                {"id": 3, "name": "Bug Origin", "value": {"id": 97, "name": "Existing"}},
                {"id": 4, "name": "Impacted", "value": "yes"},
                {"id": 5, "name": "Corrective Action", "value": "existing action"},
                {"id": 6, "name": "Resolution", "value": "existing resolution"},
            ],
        }

        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            actual_hours=1.5,
            estimated_hours=1,
            today=date(2026, 6, 2),
        )

        payload = result["payload"]
        self.assertNotIn("startDate", payload)
        self.assertNotIn("dueDate", payload)
        self.assertNotIn("estimatedHours", payload)
        self.assertNotIn("actualHours", payload)
        self.assertNotIn("customField_1", payload)
        self.assertNotIn("customField_2", payload)
        self.assertNotIn("customField_3", payload)
        self.assertEqual("no", payload["customField_4"])
        self.assertEqual("fixed save fails", payload["customField_5"])
        self.assertNotIn("customField_6", payload)


if __name__ == "__main__":
    unittest.main()
