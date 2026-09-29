import unittest
from datetime import date
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from workflows import resolve_bug as bug_workflow
from workflows.bug_template import issue_context, bug_description_metadata, parse_bug_description


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
                "corrective_action": "fixed {description}",
                "expected_detected_role": "Tester",
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

    def test_issue_context_includes_structured_description(self):
        context = issue_context(BUG_ISSUE)

        self.assertEqual("AQM-123", context["issueKey"])
        self.assertEqual("Save fails", context["summary"])
        self.assertEqual("In Progress", context["status"])
        self.assertEqual("Error appears", context["description"]["actual"])
        self.assertEqual([], context["descriptionMeta"]["missingSections"])
        self.assertEqual("Reporter", context["createdUser"])

    def test_build_resolution_plan_keeps_semantic_field_names(self):
        planned = bug_workflow.build_resolution_plan(
            CONFIG,
            "AQM-123",
            today=date(2026, 6, 2),
            actual_hours=1.5,
            comment="Fixed save issue",
        )

        plan = planned["plan"]
        self.assertEqual("Resolved", plan.status)
        self.assertEqual(1001, plan.assignee_id)
        self.assertEqual("2026-06-02", plan.start_date)
        self.assertEqual("2026-06-04", plan.due_date)
        self.assertEqual(1.5, plan.actual_hours)
        self.assertEqual("Fixed save issue", plan.comment)
        self.assertEqual(
            {
                "qc_activity": "Integration Test",
                "cause_category": "Not Applicable",
                "bug_origin": "FUN_Incomplete Function",
                "resolution": "fixed",
                "impacted": "no",
                "corrective_action": "fixed Save fails",
            },
            plan.custom_fields,
        )
        self.assertFalse(any(key.startswith("customField_") for key in plan.custom_fields))

    def test_resolution_plan_mapper_is_only_backlog_wire_translation_step(self):
        plan = bug_workflow.ResolutionPlan(
            status="Resolved",
            assignee_id=1001,
            start_date="2026-06-02",
            custom_fields={
                "qc_activity": "Integration Test",
                "corrective_action": "fixed Save fails",
            },
        )

        payload = bug_workflow.resolution_plan_to_payload(PROJECT, plan)

        self.assertEqual(4, payload["statusId"])
        self.assertEqual(1001, payload["assigneeId"])
        self.assertEqual("2026-06-02", payload["startDate"])
        self.assertEqual(10, payload["customField_1"])
        self.assertEqual("fixed Save fails", payload["customField_5"])

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
        self.assertEqual("fixed Save fails", payload["customField_5"])
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

    def test_resolve_bug_preserves_technical_identifier_casing_in_fix_description(self):
        fix_description = (
            "Handle OTP_INVALID and keep retryAfterSeconds in SomeFile.tsx unchanged."
        )

        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            fix_description=fix_description,
        )

        self.assertEqual(
            "fixed handle OTP_INVALID and keep retryAfterSeconds in SomeFile.tsx unchanged.",
            result["payload"]["customField_5"],
        )

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

        self.assertEqual("fixed Layout broken", result["payload"]["customField_5"])

    def test_resolve_dry_run_includes_changes_and_warnings(self):
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))

        change_keys = {change["key"] for change in result["changes"]}
        self.assertIn("statusId", change_keys)
        self.assertIn("customField_5", change_keys)  # corrective_action
        # The summary fallback is the intended default, not something to warn about.
        self.assertFalse(any("fix_description" in w for w in result["warnings"]))

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

    def test_detected_role_is_not_checked_without_config(self):
        workflow = {**bug_workflow.load_workflow_config.return_value}
        workflow.pop("expected_detected_role")
        bug_workflow.load_workflow_config.return_value = workflow
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "customFields": [{"id": 7, "name": "Detected Role", "value": [{"id": 1, "name": "Developer"}]}],
        }
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="x")
        self.assertFalse(any("Detected Role" in warning for warning in result["warnings"]))

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
        self.assertNotIn("customField_5", payload)  # existing Corrective Action kept without fix_description
        self.assertNotIn("customField_6", payload)


    def _issue_with_existing_guided_fields(self):
        return {
            **BUG_ISSUE,
            "estimatedHours": 2,
            "actualHours": 3,
            "customFields": [
                {"id": 1, "name": "QC Activity", "value": {"id": 10, "name": "Integration Test"}},
                {"id": 2, "name": "Cause Category", "value": {"id": 20, "name": "Not Applicable"}},
                {"id": 3, "name": "Bug Origin", "value": {"id": 30, "name": "FUN_Incomplete Function"}},
            ],
        }

    def test_resolve_warns_when_explicit_guided_value_is_not_applied(self):
        self.client.get_issue.return_value = self._issue_with_existing_guided_fields()

        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            cause_category="Not Applicable",
            estimated_hours=1,
            actual_hours=1,
            fix_description="save button validation",
        )

        self.assertNotIn("customField_2", result["payload"])
        self.assertNotIn("estimatedHours", result["payload"])
        warnings = " ".join(result["warnings"])
        self.assertIn("cause_category 'Not Applicable' was not applied", warnings)
        self.assertIn("estimated_hours 1 was not applied", warnings)
        self.assertIn("actual_hours 1 was not applied", warnings)

    def test_resolve_rejects_invalid_explicit_value_even_when_field_is_set(self):
        # Seen in production: a Bug Origin option passed as cause_category was
        # silently dropped because the issue already had a Cause Category.
        self.client.get_issue.return_value = self._issue_with_existing_guided_fields()

        with self.assertRaisesRegex(ValueError, "COD_Coding Logic"):
            bug_workflow.resolve_bug(
                CONFIG,
                "AQM-123",
                dry_run=True,
                today=date(2026, 6, 2),
                cause_category="COD_Coding Logic",
            )

    def test_resolve_apply_without_fix_description_uses_summary(self):
        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        payload = self.client.update_issue.call_args.args[1]
        self.assertEqual("fixed Save fails", payload["customField_5"])
        self.assertEqual("Resolved", result["updated"]["status"]["name"])
        self.assertFalse(any("fix_description" in w for w in result["warnings"]))

    def test_resolve_without_fix_description_keeps_existing_corrective_action(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "customFields": [{"id": 5, "field": "customField_5", "value": "fixed validation for long input"}],
        }
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))
        self.assertNotIn("customField_5", result["payload"])
        # Reporters sometimes prefill another bug's note (OOP-12798), so the kept value is reported.
        self.assertTrue(any(
            "Kept the existing Corrective Action 'fixed validation for long input'" in w for w in result["warnings"]
        ))

    def test_resolve_treats_dash_corrective_action_as_empty(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "customFields": [{"id": 5, "field": "customField_5", "value": "-"}],
        }
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))
        self.assertEqual("fixed Save fails", result["payload"]["customField_5"])
        self.assertFalse(any("kept the existing Corrective Action" in w for w in result["warnings"]))

    def test_resolve_with_fix_description_overwrites_existing_corrective_action(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE,
            "customFields": [{"id": 5, "field": "customField_5", "value": "fixed old note"}],
        }
        result = bug_workflow.resolve_bug(
            CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="save button validation"
        )
        self.assertEqual("fixed save button validation", result["payload"]["customField_5"])

    def test_resolved_bug_still_assigned_to_me_is_handed_to_reporter(self):
        # Resolved = status set AND the bug is back with QC; the status alone is not done.
        self.client.get_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        payload = self.client.update_issue.call_args.args[1]
        self.assertEqual(1001, payload["assigneeId"])
        self.assertEqual(
            [{"field": "Assignee", "from": "Me", "to": "Reporter"}],
            [c for c in bug_workflow.public_changes(result["changes"]) if c["field"] in ("Status", "Assignee")],
        )

    def test_resolve_already_resolved_bug_assigned_to_reporter_sends_no_patch(self):
        self.client.get_issue.return_value = {
            **BUG_ISSUE, "status": {"name": "Resolved"}, "assignee": {"id": 1001, "name": "Reporter"},
        }
        with self.assertRaisesRegex(ValueError, "already 'Resolved' and assigned to Reporter.*update_issue"):
            bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        self.client.update_issue.assert_not_called()

    def test_commit_note_shortens_full_shas(self):
        self.assertEqual(
            "Commit: aa2e937, ef48ffe.",
            bug_workflow.comment_with_commit(commit="aa2e9378250cd229359ce6f74313f083f3c57f4a, ef48ffe"),
        )

    def test_resolve_apply_on_excluded_status_sends_no_patch(self):
        self.client.get_issue.return_value = {**BUG_ISSUE, "status": {"name": "Closed"}}
        with self.assertRaisesRegex(ValueError, "excluded status"):
            bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2))
        self.client.update_issue.assert_not_called()

    def test_changes_show_option_names_for_select_fields(self):
        result = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2))
        qc = next(c for c in result["changes"] if c["key"] == "customField_1")
        self.assertEqual(10, result["payload"]["customField_1"])
        self.assertEqual("Integration Test", qc["value"])

    def test_public_changes_drop_no_op_entries(self):
        changes = [
            {"field": "Impacted", "key": "customField_4", "from": "no", "value": "no"},
            {"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"},
        ]
        self.assertEqual([{"field": "Status", "from": "Open", "to": "Resolved"}], bug_workflow.public_changes(changes))

    def test_public_changes_shape(self):
        changes = [
            {"field": "Status", "key": "statusId", "from": "Open", "value": "Resolved"},
            {"field": "Assignee", "key": "assigneeId", "from": {"id": 1, "name": "Dev"}, "value": {"id": 2, "name": "QC"}, "source": "createdUser"},
            {"field": "Start Date", "key": "startDate", "value": "2026-06-02"},
        ]
        self.assertEqual([
            {"field": "Status", "from": "Open", "to": "Resolved"},
            {"field": "Assignee", "from": "Dev", "to": "QC"},
            {"field": "Start Date", "from": None, "to": "2026-06-02"},
        ], bug_workflow.public_changes(changes))

    def test_corrective_action_does_not_duplicate_fixed_verb(self):
        for fix_description in ("Fixed save button validation", "fix: save button validation"):
            result = bug_workflow.resolve_bug(
                CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description=fix_description
            )
            self.assertEqual("fixed save button validation", result["payload"]["customField_5"])

        result = bug_workflow.resolve_bug(
            CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="Fixed-width layout"
        )
        self.assertEqual("fixed Fixed-width layout", result["payload"]["customField_5"])

    def test_corrective_action_lowercases_only_a_plain_leading_word(self):
        cases = {
            "Guard partner activation": "fixed guard partner activation",
            "MetaMask connector": "fixed MetaMask connector",
            "OTP_INVALID message": "fixed OTP_INVALID message",
            "UserNav.tsx layout": "fixed UserNav.tsx layout",
        }
        for fix_description, expected in cases.items():
            result = bug_workflow.resolve_bug(
                CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description=fix_description
            )
            self.assertEqual(expected, result["payload"]["customField_5"])

    def test_corrective_action_renders_bulleted_description_as_list(self):
        result = bug_workflow.resolve_bug(
            CONFIG,
            "AQM-123",
            dry_run=True,
            today=date(2026, 6, 2),
            fix_description="- UserNav.tsx: split name and email\n- admin-profile-dialog.tsx: move role Badge",
        )

        self.assertEqual(
            "fixed:\n- UserNav.tsx: split name and email\n- admin-profile-dialog.tsx: move role Badge",
            result["payload"]["customField_5"],
        )

    def test_resolve_records_mutation_for_preview_and_apply(self):
        from backlog_tool import telemetry

        self.client.update_issue.return_value = {**BUG_ISSUE, "status": {"name": "Resolved"}}
        telemetry.start_call("resolve_bug", {"issue_key": "AQM-123"})
        preview = bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=True, today=date(2026, 6, 2), fix_description="x")
        telemetry.start_call("resolve_bug", {"issue_key": "AQM-123", "mode": "apply"})
        with mock.patch.object(bug_workflow, "record_mutation") as record:
            bug_workflow.resolve_bug(CONFIG, "AQM-123", dry_run=False, today=date(2026, 6, 2), fix_description="x")
        telemetry.finish_call("ok")

        applied = record.call_args.kwargs
        self.assertEqual("apply", applied["mode"])
        self.assertEqual(telemetry.plan_hash("AQM-123", preview["payload"]), applied["planHash"])
        self.assertEqual("In Progress", applied["statusBefore"])
        self.assertEqual("Resolved", applied["statusAfter"])
        self.assertIn("statusId", applied["changedFields"])


if __name__ == "__main__":
    unittest.main()


def test_issue_context_lists_attachments():
    from workflows.bug_template import issue_context

    issue = {"issueKey": "OOP-1", "attachments": [
        {"id": 7001, "name": "login-error.png", "size": 48213, "created": "x"},
        {"id": 7002, "name": "server.log", "size": 900},
    ]}
    assert issue_context(issue)["attachments"] == [
        {"id": 7001, "name": "login-error.png", "size": 48213, "isImage": True},
        {"id": 7002, "name": "server.log", "size": 900, "isImage": False},
    ]


def test_issue_context_without_attachments_has_no_key():
    from workflows.bug_template import issue_context

    for issue in ({"issueKey": "OOP-1"}, {"issueKey": "OOP-1", "attachments": None}, {"issueKey": "OOP-1", "attachments": []}):
        assert "attachments" not in issue_context(issue)


def test_attachment_summary_skips_malformed_entries():
    from workflows.bug_template import attachment_summary

    assert attachment_summary([None, "x", {"id": 1, "name": "a.PNG", "size": 3}]) == [
        {"id": 1, "name": "a.PNG", "size": 3, "isImage": True},
    ]


def test_issue_context_keeps_raw_description_only_when_sections_are_missing():
    from workflows.bug_template import issue_context

    parsed = issue_context(BUG_ISSUE)
    assert parsed["descriptionMeta"]["missingSections"] == []
    assert "rawDescription" not in parsed

    # A description outside the template (a Story, a free-text bug) stays plain text.
    free_text = issue_context({"issueKey": "OOP-1", "description": "Login fails after reset"})
    assert free_text["description"] == "Login fails after reset"
    assert "descriptionMeta" not in free_text and "rawDescription" not in free_text

    partial = issue_context({"issueKey": "OOP-1", "description": "**Actual:\nOnly actual"})
    assert partial["description"] == {"actual": "Only actual"}
    assert partial["rawDescription"] == "**Actual:\nOnly actual"


def test_issue_context_compacts_custom_fields_and_links_the_issue():
    from workflows.bug_template import issue_context

    issue = {"issueKey": "OOP-1", "customFields": [
        {"id": 9864, "fieldTypeId": 5, "name": "QC Activity", "value": {"id": 1, "name": "Integration Test", "displayOrder": 0}},
        {"id": 9865, "fieldTypeId": 1, "name": "Empty", "value": None},
    ]}
    context = issue_context(issue, base_url="https://space.backlog.com/")
    assert context["customFields"] == [{"name": "QC Activity", "value": "Integration Test"}]
    assert context["url"] == "https://space.backlog.com/view/OOP-1"
