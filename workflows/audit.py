#!/usr/bin/env python3
from string import Formatter

from backlog_tool.resolver import (
    category_options,
    find_option,
    issue_type_options,
    resolve_custom_field_defaults,
    status_options,
)
from backlog_tool.settings import load_project_catalog, load_workflow_config, project_keys
from .resolve_policy import (
    ALWAYS_OVERWRITE_FIELDS,
    GUIDED_FIELDS,
    ONLY_WHEN_EMPTY_FIELDS,
    WORKFLOW_MANAGED_FIELDS,
    OPTIONAL_FIELDS,
)
from .ut_bug import merge_bug_defaults


REQUIRED_KEYS = {
    "resolve_bug": {
        "issue_type",
        "excluded_statuses",
        "status",
        "assignee",
        "estimated_hours",
        "actual_hours",
        "due_in_days",
        "corrective_action",
        "custom_fields",
    },
    "story_task_overview": {
        "issue_types",
        "excluded_statuses",
        "assignee",
        "fields",
    },
    "ut_bug": {
        "issue_type",
        "status",
        "estimated_hours",
        "actual_hours",
        "due_in_days",
        "corrective_action",
        "description_template",
        "custom_fields",
    },
}

STORY_OUTPUT_FIELDS = {
    "issueKey",
    "summary",
    "description",
    "status",
    "dueDate",
    "daysUntilDue",
    "dueAlertLevel",
}

CORRECTIVE_ACTION_PLACEHOLDERS = {"description", "description_lower"}


def template_fields(template):
    return {
        field_name
        for _literal, field_name, _format_spec, _conversion in Formatter().parse(template)
        if field_name
    }


def audit_workflows(config):
    checks = []
    errors = []
    workflows = {
        name: load_workflow_config(name)
        for name in REQUIRED_KEYS
    }

    # Check story_task_overview required keys at root (no project_overrides support)
    story_keys = REQUIRED_KEYS["story_task_overview"]
    missing = sorted(story_keys - set(workflows["story_task_overview"]))
    checks.append("story_task_overview: required keys")
    if missing:
        errors.append(f"story_task_overview missing required keys: {', '.join(missing)}")

    # Policy field groups checks
    field_groups = set(ALWAYS_OVERWRITE_FIELDS) | set(ONLY_WHEN_EMPTY_FIELDS)
    checks.append("resolve_bug: policy field groups")
    if not set(GUIDED_FIELDS).issubset(ONLY_WHEN_EMPTY_FIELDS):
        errors.append("resolve_bug guided fields must be only-when-empty fields")
    if set(WORKFLOW_MANAGED_FIELDS) != set(ALWAYS_OVERWRITE_FIELDS) | {"resolution"}:
        errors.append("resolve_bug workflow-managed fields do not match execution policy")

    for workflow_name in ("resolve_bug", "ut_bug"):
        workflow = workflows[workflow_name]
        placeholders = template_fields(workflow["corrective_action"])
        checks.append(f"{workflow_name}: corrective-action template")
        unknown = sorted(placeholders - CORRECTIVE_ACTION_PLACEHOLDERS)
        if unknown:
            errors.append(
                f"{workflow_name} corrective_action has unsupported placeholders: "
                + ", ".join(unknown)
            )

    story_fields = set(workflows["story_task_overview"]["fields"])
    checks.append("story_task_overview: output fields")
    unknown_story_fields = sorted(story_fields - STORY_OUTPUT_FIELDS)
    if unknown_story_fields:
        errors.append(
            "story_task_overview has unsupported fields: "
            + ", ".join(unknown_story_fields)
        )

    for project_key in project_keys(config):
        project = load_project_catalog(project_key)
        checks.append(f"{project_key}: resolve_bug catalog compatibility")
        try:
            from workflows.resolve_bug import merge_resolve_defaults
            resolve_workflow = merge_resolve_defaults(config, project_key)

            # Check required keys for this project's resolve_bug
            resolve_keys = set(REQUIRED_KEYS["resolve_bug"])
            missing_keys = sorted(resolve_keys - set(resolve_workflow))
            if missing_keys:
                raise ValueError(f"missing required keys: {', '.join(missing_keys)}")

            project_fields = project.get("bug", {}).get("custom_fields", {})
            required_resolve_fields = (
                set(ALWAYS_OVERWRITE_FIELDS)
                | set(GUIDED_FIELDS)
            )
            if "cause_category" in required_resolve_fields and "bug_category" in project_fields and "cause_category" not in project_fields:
                required_resolve_fields = (required_resolve_fields - {"cause_category"}) | {"bug_category"}
            missing_resolve_fields = sorted(
                required_resolve_fields - set(project_fields)
            )
            if missing_resolve_fields:
                raise ValueError(
                    "missing required custom fields: "
                    + ", ".join(missing_resolve_fields)
                )

            # Check missing policy field defaults for this project
            resolve_custom_fields = resolve_workflow.get("custom_fields", {})
            resolve_all_fields = set(resolve_custom_fields) | set(resolve_workflow)
            cause_key = "bug_category" if "bug_category" in project_fields else "cause_category"
            project_field_groups = {
                ("bug_category" if f == "cause_category" and cause_key == "bug_category" else f)
                for f in field_groups
            }
            required_policy_fields = {
                f for f in project_field_groups
                if f in project_fields or f not in OPTIONAL_FIELDS
            }
            missing_field_defaults = sorted(required_policy_fields - resolve_all_fields)
            if missing_field_defaults:
                raise ValueError(
                    "missing policy field defaults: "
                    + ", ".join(missing_field_defaults)
                )

            find_option(
                issue_type_options(project),
                resolve_workflow["issue_type"],
                "issue type",
            )
            find_option(
                status_options(project),
                resolve_workflow["status"],
                "status",
            )
            selections = {}
            for field_key in project_field_groups:
                if field_key == "resolution" and field_key not in project_fields:
                    continue
                selections[field_key] = resolve_custom_fields.get(field_key)
            resolve_custom_field_defaults(
                project,
                selections,
            )
        except ValueError as error:
            errors.append(f"{project_key} resolve_bug: {error}")

        checks.append(f"{project_key}: ut_bug catalog compatibility")
        try:
            ut_defaults = merge_bug_defaults(config, project_key)

            # Check required keys for this project's ut_bug
            ut_keys = set(REQUIRED_KEYS["ut_bug"])
            missing_keys = sorted(ut_keys - set(ut_defaults))
            if missing_keys:
                raise ValueError(f"missing required keys: {', '.join(missing_keys)}")

            find_option(
                issue_type_options(project),
                ut_defaults["issue_type"],
                "issue type",
            )
            find_option(
                status_options(project),
                ut_defaults["status"],
                "status",
            )
            if ut_defaults.get("category"):
                find_option(
                    category_options(project),
                    ut_defaults["category"],
                    "category",
                )
            resolve_custom_field_defaults(
                project,
                ut_defaults["custom_fields"],
            )
        except ValueError as error:
            errors.append(f"{project_key} ut_bug: {error}")

    if errors:
        raise ValueError("Workflow audit failed: " + " | ".join(errors))
    return {
        "ok": True,
        "checks": checks,
        "workflowCount": len(workflows),
        "projectCount": len(project_keys(config)),
    }
