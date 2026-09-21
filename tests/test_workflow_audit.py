import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflows import audit


CONFIG = {
    "projects": ["AQM"],
}

PROJECT = {
    "key": "AQM",
    "bug": {
        "issue_type_options": [{"id": 1, "name": "Bug"}],
        "status_options": [
            {"id": 3, "name": "Resolved"},
            {"id": 4, "name": "Closed"},
        ],
        "custom_fields": {
            "qc_activity": {
                "field": "customField_1",
                "value_options": [{"id": 1, "name": "Integration Test"}, {"id": 2, "name": "Unit Test"}],
            },
            "cause_category": {
                "field": "customField_2",
                "value_options": [{"id": 1, "name": "Not Applicable"}],
            },
            "bug_origin": {
                "field": "customField_3",
                "value_options": [
                    {"id": 1, "name": "FUN_Incomplete Function"},
                    {"id": 2, "name": "COD_Other"},
                ],
            },
            "impacted": {"field": "customField_4"},
            "corrective_action": {"field": "customField_5"},
            "resolution": {"field": "customField_6"},
            "detected_role": {
                "field": "customField_7",
                "value_options": [{"id": 1, "name": "Developer"}],
            },
        },
    },
}

RESOLVE_WORKFLOW = {
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
}

UT_WORKFLOW = {
    "issue_type": "Bug",
    "status": "Closed",
    "estimated_hours": 1,
    "actual_hours": 1,
    "due_in_days": 2,
    "corrective_action": "fixed {description_lower}",
    "description_template": "description",
    "custom_fields": {
        "qc_activity": "Unit Test",
        "bug_origin": "COD_Other",
        "cause_category": "Not Applicable",
        "impacted": "no",
        "detected_role": "Developer",
    },
}

STORY_WORKFLOW = {
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
}


class WorkflowAuditTest(unittest.TestCase):
    def setUp(self):
        workflows = {
            "resolve_bug": RESOLVE_WORKFLOW,
            "ut_bug": UT_WORKFLOW,
            "story_task_overview": STORY_WORKFLOW,
        }
        mock.patch.object(audit, "load_workflow_config", side_effect=workflows.get).start()
        from workflows import resolve_bug
        mock.patch.object(resolve_bug, "load_workflow_config", return_value=RESOLVE_WORKFLOW).start()
        mock.patch.object(audit, "load_project_catalog", return_value=PROJECT).start()
        mock.patch.object(audit, "project_keys", return_value=["AQM"]).start()
        mock.patch.object(audit, "merge_bug_defaults", return_value=UT_WORKFLOW).start()
        self.addCleanup(mock.patch.stopall)

    def test_audit_accepts_synchronized_workflows(self):
        result = audit.audit_workflows(CONFIG)

        self.assertTrue(result["ok"])
        self.assertEqual(3, result["workflowCount"])
        self.assertEqual(1, result["projectCount"])

    def test_audit_rejects_unknown_template_placeholder(self):
        invalid_workflow = {
            **RESOLVE_WORKFLOW,
            "corrective_action": "fixed {unknown}",
        }
        audit.load_workflow_config.side_effect = {
            "resolve_bug": invalid_workflow,
            "ut_bug": UT_WORKFLOW,
            "story_task_overview": STORY_WORKFLOW,
        }.get

        with self.assertRaisesRegex(ValueError, "unsupported placeholders: unknown"):
            audit.audit_workflows(CONFIG)

    def test_audit_rejects_missing_required_project_field(self):
        audit.load_project_catalog.return_value = {
            **PROJECT,
            "bug": {
                **PROJECT["bug"],
                "custom_fields": {
                    key: value
                    for key, value in PROJECT["bug"]["custom_fields"].items()
                    if key != "corrective_action"
                },
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "missing required custom fields: corrective_action",
        ):
            audit.audit_workflows(CONFIG)


if __name__ == "__main__":
    unittest.main()
