import unittest
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflows import guidance


WORKFLOW = {
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


class GuidanceTest(unittest.TestCase):
    def setUp(self):
        mock.patch.object(guidance, "load_workflow_config", return_value=WORKFLOW).start()
        self.addCleanup(mock.patch.stopall)

    def test_resolve_rules_sourced_from_config(self):
        rules = guidance.resolve_rules()

        self.assertIn("Resolved", rules["actions"][0])
        self.assertEqual("Bug", rules["appliesTo"]["issueType"])
        self.assertEqual("me", rules["appliesTo"]["assignee"])
        self.assertEqual(["Closed"], rules["appliesTo"]["excludedStatuses"])
        self.assertEqual("Integration Test", rules["defaults"]["qc_activity"])
        self.assertIn("impacted", rules["alwaysOverwrite"])
        self.assertIn("corrective_action", rules["alwaysOverwrite"])
        self.assertIn("--commit", rules["overrides"])
        self.assertIn("resolution", rules["fieldGuidance"]["workflowManaged"])
        self.assertTrue(any("effective startDate" in action for action in rules["actions"]))

    def test_field_guidance_lists_fields_when_no_arg(self):
        result = guidance.field_guidance()

        self.assertIn("qc_activity", result["fields"])
        self.assertIn("bug_origin", result["fields"])
        self.assertIn("corrective_action", result["workflowManagedFields"])

    def test_field_guidance_returns_options_for_known_field(self):
        result = guidance.field_guidance("bug_origin")

        self.assertEqual("bug_origin", result["field"])
        self.assertEqual("FUN_Incomplete Function", result["default"])
        self.assertIn("UI_Layout", result["options"])

    def test_field_guidance_uses_project_override_defaults(self):
        workflow = {
            **WORKFLOW,
            "custom_fields": {},
            "project_overrides": {
                "VTO": {
                    "custom_fields": {
                        "bug_origin": "FUN_Wrong Business Logic",
                        "bug_category": "Not Applicable",
                    },
                },
            },
        }
        config = {"projects": ["VTO"]}

        with mock.patch.object(guidance, "load_workflow_config", return_value=workflow):
            result = guidance.field_guidance("bug_origin", config, "VTO")
            cause = guidance.field_guidance("cause_category", config, "VTO")

        self.assertEqual("FUN_Wrong Business Logic", result["default"])
        self.assertEqual("Not Applicable", cause["default"])

    def test_field_guidance_requires_project_when_config_has_no_default(self):
        config = {"projects": ["VTO"]}

        with self.assertRaisesRegex(ValueError, "Cannot determine Backlog project"):
            guidance.field_guidance("bug_origin", config)

    def test_field_guidance_rejects_unknown_field(self):
        with self.assertRaises(ValueError):
            guidance.field_guidance("nope")


if __name__ == "__main__":
    unittest.main()
