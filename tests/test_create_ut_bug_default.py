import unittest
from datetime import datetime, timedelta
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from workflows import ut_bug as backlog_ut_bug_service


CONFIG = {
    "base_url": "https://example.backlog.com",
    "default_project_key": "OOP",
    "projects": ["OOP"],
    "users": {
        "me": {"id": 778617},
    },
    "defaults": {
        "assignee": "me",
        "priority_id": 3,
    },
}


UT_BUG_WORKFLOW = {
    "issue_type": "Bug",
    "status": "Closed",
    "estimated_hours": 1,
    "actual_hours": 1,
    "due_in_days": 2,
    "corrective_action": "fixed {description_lower}",
    "description_template": "**Environment**:\n\n**Actual**:\n",
    "custom_fields": {
        "qc_activity": "Unit Test",
        "bug_origin": "COD_Other",
        "detected_role": "Developer",
    },
    "project_overrides": {
        "OOP": {
            "category": "112_DHP",
        },
    },
}


PROJECT = {
    "key": "OOP",
    "id": 82531,
    "bug": {
        "issue_type_options": [
            {"id": 351795, "name": "Bug"},
        ],
        "category_options": [
            {"id": 165807, "name": "112_DHP"},
        ],
        "status_options": [
            {"id": 4, "name": "Closed"},
        ],
        "custom_fields": {
            "qc_activity": {
                "label": "QC Activity",
                "field": "customField_9864",
                "value_options": [
                    {"id": 7, "name": "Unit Test"},
                ],
            },
            "bug_origin": {
                "label": "Bug Origin",
                "field": "customField_10150",
                "value_options": [
                    {"id": 6, "name": "COD_Other"},
                ],
            },
            "detected_role": {
                "label": "Detected Role",
                "field": "customField_10160",
                "value_options": [
                    {"id": 8, "name": "Developer"},
                ],
            },
            "corrective_action": {
                "label": "Corrective Action",
                "field": "customField_10200",
            },
        },
    },
}


class FixedDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 6, 2, 8, 0, 0)


class CreateUtBugDefaultTest(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.get_issue.return_value = {"id": 12345}
        self.client.get_project_id.return_value = 82531
        self.client.create_issue.return_value = {
            "issueKey": "OOP-999",
            "createdUser": {"id": 778617},
        }
        self.client.update_issue.return_value = {
            "issueKey": "OOP-999",
            "status": {"name": "Closed"},
        }

        mock.patch.object(backlog_ut_bug_service, "resolve_project", return_value=PROJECT).start()
        mock.patch.object(backlog_ut_bug_service, "BacklogClient", return_value=self.client).start()
        mock.patch.object(backlog_ut_bug_service, "load_workflow_config", return_value=UT_BUG_WORKFLOW).start()
        mock.patch.object(backlog_ut_bug_service, "log_event").start()
        self.addCleanup(mock.patch.stopall)

    def test_build_subtask_bug_payload_uses_defaults_parent_and_corrective_action(self):
        with mock.patch.object(
            backlog_ut_bug_service,
            "datetime",
            FixedDateTime,
        ):
            result = backlog_ut_bug_service.build_subtask_bug_payload(
                CONFIG,
                "OOP",
                "OOP-123",
                "A020100|FE",
                "Button broken",
            )

        self.client.get_issue.assert_called_once_with("OOP-123")
        payload = result["payload"]
        expected_due = FixedDateTime.now() + timedelta(days=2)

        self.assertEqual("OOP", result["project"])
        self.assertEqual("OOP-123", result["parentIssueKey"])
        self.assertEqual(12345, result["parentIssueId"])
        self.assertEqual(82531, payload["projectId"])
        self.assertEqual("[OOP-123][A020100|FE] Button broken", payload["summary"])
        self.assertIn("**Environment**:", payload["description"])
        self.assertIn("**Actual**:", payload["description"])
        self.assertEqual(12345, payload["parentIssueId"])
        self.assertEqual(351795, payload["issueTypeId"])
        self.assertNotIn("statusId", payload)
        self.assertEqual({"statusId": 4, "assigneeId": 778617}, result["postCreatePayload"])
        self.assertEqual([165807], payload["categoryId[]"])
        self.assertEqual(778617, payload["assigneeId"])
        self.assertEqual("2026-06-02", payload["startDate"])
        self.assertEqual(expected_due.strftime("%Y-%m-%d"), payload["dueDate"])
        self.assertEqual(1, payload["estimatedHours"])
        self.assertEqual(1, payload["actualHours"])
        self.assertEqual(7, payload["customField_9864"])
        self.assertEqual(6, payload["customField_10150"])
        self.assertEqual(8, payload["customField_10160"])
        self.assertEqual("fixed button broken", payload["customField_10200"])

    def test_create_subtask_bug_dry_run_does_not_post(self):
        result = backlog_ut_bug_service.create_subtask_bug(
            CONFIG,
            "OOP",
            "OOP-123",
            "A020100|FE",
            "Button broken",
            dry_run=True,
        )

        self.client.create_issue.assert_not_called()
        self.client.update_issue.assert_not_called()
        self.assertTrue(result["dryRun"])
        self.assertEqual("OOP", result["project"])
        self.assertEqual({"statusId": 4, "assigneeId": 778617}, result["postCreatePayload"])

    def test_create_subtask_bug_posts_then_updates_status_closed(self):
        result = backlog_ut_bug_service.create_subtask_bug(
            CONFIG,
            "OOP",
            "OOP-123",
            "A020100|FE",
            "Button broken",
            dry_run=False,
        )

        self.client.create_issue.assert_called_once()
        create_payload = self.client.create_issue.call_args.args[0]
        self.assertNotIn("statusId", create_payload)
        self.client.update_issue.assert_called_once_with(
            "OOP-999",
            {"statusId": 4, "assigneeId": 778617},
        )
        self.assertEqual("OOP-999", result["issueKey"])

    def test_create_subtask_bug_rejects_create_response_without_issue_key(self):
        self.client.create_issue.return_value = {
            "createdUser": {"id": 778617},
        }

        with self.assertRaisesRegex(ValueError, "missing issueKey"):
            backlog_ut_bug_service.create_subtask_bug(
                CONFIG,
                "OOP",
                "OOP-123",
                "A020100|FE",
                "Button broken",
                dry_run=False,
            )

    def test_create_subtask_bug_reports_created_issue_when_close_update_fails(self):
        self.client.update_issue.side_effect = RuntimeError("PATCH /issues/OOP-999 failed")

        with self.assertRaises(backlog_ut_bug_service.PostCreateUpdateError) as raised:
            backlog_ut_bug_service.create_subtask_bug(
                CONFIG,
                "OOP",
                "OOP-123",
                "A020100|FE",
                "Button broken",
                dry_run=False,
            )

        self.assertEqual("OOP-999", raised.exception.issue_key)
        self.assertEqual({"statusId": 4, "assigneeId": 778617}, raised.exception.payload)
        self.assertEqual("Closed", raised.exception.target_status)
        self.assertIn("Created UT bug OOP-999", str(raised.exception))

    def test_unknown_default_custom_field_fails_instead_of_silent_skip(self):
        bad_workflow = {
            **UT_BUG_WORKFLOW,
            "custom_fields": {
                "missing": "value",
            },
            "project_overrides": {},
        }

        with mock.patch.object(backlog_ut_bug_service, "load_workflow_config", return_value=bad_workflow):
            with self.assertRaisesRegex(ValueError, "Unknown custom field"):
                backlog_ut_bug_service.build_subtask_bug_payload(
                    CONFIG,
                    "OOP",
                    "OOP-123",
                    "A020100|FE",
                    "Button broken",
                )

    def test_unknown_status_label_fails_instead_of_silent_skip(self):
        bad_workflow = {
            **UT_BUG_WORKFLOW,
            "status": "Not A Status",
        }

        with mock.patch.object(backlog_ut_bug_service, "load_workflow_config", return_value=bad_workflow):
            with self.assertRaisesRegex(ValueError, "Unknown status"):
                backlog_ut_bug_service.build_subtask_bug_payload(
                    CONFIG,
                    "OOP",
                    "OOP-123",
                    "A020100|FE",
                    "Button broken",
                )

    def test_unknown_project_category_fails_instead_of_silent_skip(self):
        bad_workflow = {
            **UT_BUG_WORKFLOW,
            "project_overrides": {
                "OOP": {
                    "category": "Missing Category",
                },
            },
        }

        with mock.patch.object(backlog_ut_bug_service, "load_workflow_config", return_value=bad_workflow):
            with self.assertRaisesRegex(ValueError, "Unknown category"):
                backlog_ut_bug_service.build_subtask_bug_payload(
                    CONFIG,
                    "OOP",
                    "OOP-123",
                    "A020100|FE",
                    "Button broken",
                )

    def test_project_without_category_override_does_not_set_category(self):
        workflow = {
            **UT_BUG_WORKFLOW,
            "project_overrides": {},
        }

        with mock.patch.object(backlog_ut_bug_service, "load_workflow_config", return_value=workflow):
            result = backlog_ut_bug_service.build_subtask_bug_payload(
                CONFIG,
                "OOP",
                "OOP-123",
                "A020100|FE",
                "Button broken",
            )

        self.assertNotIn("categoryId[]", result["payload"])


if __name__ == "__main__":
    unittest.main()
