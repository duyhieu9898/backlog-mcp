import argparse
import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backlog_tool import client as backlog_client
from backlog_tool import issue_service as backlog_issue_service


CONFIG = {
    "base_url": "https://example.backlog.com",
    "default_project_key": "AQM",
    "projects": ["AQM", "OOP"],
    "users": {
        "me": {"id": 778617},
        "reviewer": {"id": 1001},
    },
    "defaults": {
        "assignee": "me",
        "priority_id": 3,
    },
}


PROJECT = {
    "key": "OOP",
    "id": 82531,
    "bug": {
        "issue_type_options": [
            {"id": 351795, "name": "Bug"},
            {"id": 351796, "name": "Task"},
        ],
        "category_options": [
            {"id": 165807, "name": "112_DHP"},
        ],
        "custom_fields": {
            "qc_activity": {
                "label": "QC Activity",
                "field": "customField_9864",
                "value_options": [
                    {"id": 7, "name": "Unit Test"},
                ],
            },
            "plain_text": {
                "label": "Plain Text",
                "field": "customField_9999",
            },
        },
    },
}


def create_args(**overrides):
    values = {
        "project": "OOP",
        "summary": "Smoke summary",
        "issue_type": "Bug",
        "parent": None,
        "desc": None,
        "priority": None,
        "assignee": None,
        "category": None,
        "start_date": None,
        "due_date": None,
        "estimated_hours": None,
        "actual_hours": None,
        "custom": [],
        "dry_run": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def update_args(**overrides):
    values = {
        "project": "OOP",
        "issue_id": "OOP-123",
        "summary": None,
        "status": None,
        "comment": None,
        "desc": None,
        "priority": None,
        "assignee": None,
        "category": None,
        "start_date": None,
        "due_date": None,
        "estimated_hours": None,
        "actual_hours": None,
        "custom": [],
        "dry_run": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class BacklogApiPayloadTest(unittest.TestCase):
    def setUp(self):
        self.resolve_project = mock.patch.object(backlog_issue_service, "resolve_project", return_value=PROJECT).start()
        self.resolve_project_for_issue = mock.patch.object(
            backlog_issue_service,
            "resolve_project_for_issue",
            return_value=PROJECT,
        ).start()
        mock.patch.object(backlog_issue_service, "log_event").start()
        self.addCleanup(mock.patch.stopall)

    def test_create_payload_uses_explicit_category_and_custom_field_labels(self):
        args = create_args(
            desc="Description",
            category="112_DHP",
            custom=["qc_activity=Unit Test", "plain_text=free value"],
        )

        payload = backlog_issue_service.build_create_payload(CONFIG, args)

        self.resolve_project.assert_called_once_with(CONFIG, "OOP", start_path=None)
        self.assertEqual(82531, payload["projectId"])
        self.assertEqual("Smoke summary", payload["summary"])
        self.assertEqual(351795, payload["issueTypeId"])
        self.assertEqual(3, payload["priorityId"])
        self.assertEqual(778617, payload["assigneeId"])
        self.assertEqual([165807], payload["categoryId[]"])
        self.assertEqual(7, payload["customField_9864"])
        self.assertEqual("free value", payload["customField_9999"])

    def test_create_payload_does_not_apply_bug_category_when_issue_type_is_explicit(self):
        args = create_args(issue_type="Task")

        payload = backlog_issue_service.build_create_payload(CONFIG, args)

        self.assertEqual(351796, payload["issueTypeId"])
        self.assertNotIn("categoryId[]", payload)

    def test_create_payload_requires_issue_type_for_generic_create(self):
        with self.assertRaisesRegex(ValueError, "--issue-type is required"):
            backlog_issue_service.build_create_payload(CONFIG, create_args(issue_type=None))

    def test_create_payload_resolves_parent_issue_key(self):
        args = create_args(parent="OOP-123")

        with mock.patch.object(backlog_issue_service, "request_json", return_value={"id": 9876}) as request_json:
            payload = backlog_issue_service.build_create_payload(CONFIG, args)

        request_json.assert_called_once_with(CONFIG, "GET", "/issues/OOP-123")
        self.assertEqual(9876, payload["parentIssueId"])

    def test_resolve_custom_fields_rejects_unknown_field(self):
        with self.assertRaisesRegex(ValueError, "Unknown custom field"):
            backlog_issue_service.resolve_custom_fields(PROJECT, ["missing=value"])

    def test_update_payload_rejects_empty_update(self):
        with self.assertRaisesRegex(ValueError, "No update fields provided"):
            backlog_issue_service.build_update_payload(CONFIG, update_args())

        self.resolve_project_for_issue.assert_called_once_with(CONFIG, "OOP-123", "OOP", start_path=None)

    def test_update_payload_resolves_status_priority_assignee_and_category(self):
        args = update_args(
            status="In Progress",
            priority="High",
            assignee="reviewer",
            category="112_DHP",
            comment="updated by test",
        )

        def fake_request_json(config, method, path, data=None):
            if path == "/projects/OOP/statuses":
                return [{"id": 2, "name": "In Progress"}]
            if path == "/priorities":
                return [{"id": 2, "name": "High"}]
            raise AssertionError(path)

        with mock.patch.object(backlog_issue_service, "request_json", side_effect=fake_request_json):
            payload = backlog_issue_service.build_update_payload(CONFIG, args)

        self.assertEqual(2, payload["statusId"])
        self.assertEqual(2, payload["priorityId"])
        self.assertEqual(1001, payload["assigneeId"])
        self.assertEqual([165807], payload["categoryId[]"])
        self.assertEqual("updated by test", payload["comment"])
        self.resolve_project_for_issue.assert_called_with(CONFIG, "OOP-123", "OOP", start_path=None)

    def test_update_payload_uses_issue_key_to_resolve_project_when_default_differs(self):
        args = update_args(project=None, issue_id="OOP-123", comment="updated by test")

        payload = backlog_issue_service.build_update_payload(CONFIG, args)

        self.assertEqual("updated by test", payload["comment"])
        self.resolve_project_for_issue.assert_called_once_with(CONFIG, "OOP-123", None, start_path=None)

    def test_create_issue_dry_run_does_not_post(self):
        args = create_args()

        with mock.patch.object(backlog_issue_service, "request_json") as request_json:
            result = backlog_issue_service.create_issue(CONFIG, args)

        request_json.assert_not_called()
        self.assertTrue(result["dryRun"])
        self.assertEqual("Smoke summary", result["payload"]["summary"])

    def test_log_response_records_error_status_and_body_without_url(self):
        class Response:
            ok = False
            status_code = 400
            text = '{"errors":[{"message":"bad request"}]}'

        with mock.patch("backlog_tool.client.log_event") as log_event:
            backlog_client.log_response("POST", "/issues", Response())

        log_event.assert_called_once_with(
            "error",
            "api",
            method="POST",
            path="/issues",
            status=400,
            body='{"errors":[{"message":"bad request"}]}',
        )


if __name__ == "__main__":
    unittest.main()
