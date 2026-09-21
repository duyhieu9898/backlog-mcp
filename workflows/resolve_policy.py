#!/usr/bin/env python3
from datetime import date, timedelta

from .config import require_int, require_list, require_value


WORKFLOW_NAME = "resolve_bug"
ASSIGNMENT_SOURCE = "createdUser (reporter)"

GUIDED_FIELDS = ("qc_activity", "bug_origin", "cause_category")
ALWAYS_OVERWRITE_FIELDS = ("impacted", "corrective_action")
ONLY_WHEN_EMPTY_FIELDS = ("qc_activity", "cause_category", "bug_origin", "resolution")
OPTIONAL_FIELDS = ("resolution",)
PRESERVED_FIELDS = ("Detected Role", "Summary", "Description", "QC Activity (if already set)")
WORKFLOW_MANAGED_FIELDS = ("impacted", "corrective_action", "resolution")

OVERRIDES = {
    "--fix-description": "Text for Corrective Action (fixed <text>). Strongly recommended.",
    "--commit": "Commit hash/ref appended to the update comment.",
    "--qc-activity": "Override QC Activity label.",
    "--bug-origin": "Override Bug Origin label.",
    "--cause-category": "Override Cause Category label.",
    "--estimated-hours / --actual-hours": "Numeric hours.",
    "--comment": "Update comment.",
}


def resolve_rules_from_config(workflow):
    issue_type = require_value(workflow, "issue_type", WORKFLOW_NAME)
    status = require_value(workflow, "status", WORKFLOW_NAME)
    due_in_days = require_int(workflow, "due_in_days", WORKFLOW_NAME)
    excluded_statuses = require_list(workflow, "excluded_statuses", WORKFLOW_NAME)

    custom_fields = workflow.get("custom_fields", {})
    cause_key = "bug_category" if "bug_category" in custom_fields else "cause_category"

    return {
        "appliesTo": {
            "issueType": issue_type,
            "assignee": require_value(workflow, "assignee", WORKFLOW_NAME),
            "excludedStatuses": excluded_statuses,
        },
        "actions": [
            f"Set status to '{status}'.",
            f"Assign the issue back to {ASSIGNMENT_SOURCE}.",
            "Set startDate to today if missing.",
            f"Set dueDate to the effective startDate + {due_in_days} days if missing.",
            f"Set estimatedHours to --estimated-hours, else {require_value(workflow, 'estimated_hours', WORKFLOW_NAME)} if missing.",
            f"Set actualHours to --actual-hours, else {require_value(workflow, 'actual_hours', WORKFLOW_NAME)} if missing.",
        ],
        "alwaysOverwrite": list(ALWAYS_OVERWRITE_FIELDS),
        "onlyWhenEmpty": list(ONLY_WHEN_EMPTY_FIELDS),
        "doNotChange": list(PRESERVED_FIELDS),
        "defaults": {
            "qc_activity": custom_fields.get("qc_activity"),
            "cause_category": custom_fields.get(cause_key) or custom_fields.get("cause_category"),
            "bug_origin": custom_fields.get("bug_origin"),
            "impacted": custom_fields.get("impacted"),
            "resolution": custom_fields.get("resolution"),
            "corrective_action": require_value(workflow, "corrective_action", WORKFLOW_NAME),
        },
        "overrides": dict(OVERRIDES),
        "safety": [
            "resolve is dry-run by default; add --apply only after the diff is correct.",
            "The issue must match the configured issue type, assignee, and non-excluded status.",
            "If Detected Role is not Tester, say so in the summary before applying.",
            "Run `fields <field>` before choosing qc_activity, bug_origin, or cause_category.",
        ],
    }


def render_corrective_action(workflow, description):
    template = require_value(workflow, "corrective_action", WORKFLOW_NAME)
    return template.format(
        description=description,
        description_lower=description.lower(),
    )


def effective_start_date(issue_start_date, fallback_date=None):
    if issue_start_date:
        try:
            return date.fromisoformat(str(issue_start_date)[:10])
        except ValueError as error:
            raise ValueError(f"Invalid issue startDate '{issue_start_date}'.") from error
    return fallback_date or date.today()


def due_date_from_start(issue_start_date, due_in_days, fallback_date=None):
    start_date = effective_start_date(issue_start_date, fallback_date)
    return start_date + timedelta(days=due_in_days)
