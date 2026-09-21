#!/usr/bin/env python3
"""Machine-readable bug workflow rules and field guidance.

This replaces long prose docs: the agent runs `backlog.py bug rules` or
`backlog.py bug fields <field>` to load only the logic it needs, instead of
reading multiple markdown files into context.
"""

from backlog_tool.settings import load_workflow_config, resolve_project_key
from .resolve_bug import merge_resolve_defaults
from .resolve_policy import (
    GUIDED_FIELDS,
    WORKFLOW_MANAGED_FIELDS,
    resolve_rules_from_config,
)


def guidance_workflow(config=None, project_key=None, start_path=None):
    if not config:
        return load_workflow_config("resolve_bug")
    return merge_resolve_defaults(config, resolve_project_key(config, project_key, start_path=start_path))


def custom_default(custom_fields, field_key):
    if field_key == "cause_category":
        return custom_fields.get("cause_category") or custom_fields.get("bug_category")
    return custom_fields.get(field_key)


def resolve_rules(config=None, project_key=None, start_path=None):
    """Return the same policy consumed by the resolve execution workflow."""
    workflow = guidance_workflow(config, project_key, start_path=start_path)
    rules = resolve_rules_from_config(workflow)
    rules["fieldGuidance"] = {
        "supported": list(GUIDED_FIELDS),
        "workflowManaged": list(WORKFLOW_MANAGED_FIELDS),
        "note": "`bug fields` only documents selectable option fields; workflow-managed fields are shown by dry-run.",
    }
    return rules


# Compact field guidance. Labels must match project catalog value_options.
FIELD_GUIDANCE = {
    "qc_activity": {
        "summary": "How the bug was found or validated.",
        "default": "Integration Test",
        "options": {
            "Unit Test": "found/verified at unit or function level.",
            "Integration Test": "interaction between modules, APIs, DB, services, or cross-component.",
            "SystemTest": "visible in an end-to-end application flow.",
            "Acceptance Test": "tied to acceptance/customer scenario.",
            "Code Review": "found by reading code, not runtime test.",
            "Document Review": "found from document/spec review.",
            "Not Applicable": "testing activity unknown or not relevant.",
        },
    },
    "bug_origin": {
        "summary": "Concrete origin/type of the bug.",
        "default": "FUN_Incomplete Function",
        "options": {
            "COD_Coding Logic": "wrong condition, branching, loop, calculation, validation, or logic.",
            "COD_Compile": "compile/build/syntax/import/type error.",
            "COD_Hard Code": "hard-coded value causes wrong behavior.",
            "COD_Coding Standard": "coding convention/standard violation.",
            "COD_Redundancy Code": "redundant or duplicated code causes issue.",
            "COD_Other": "coding issue where no more specific COD option fits.",
            "FUN_Incomplete Function": "feature exists but implementation incomplete or misses a case.",
            "FUN_Wrong Business Logic": "conflicts with business rule or expected workflow.",
            "FUN_Feature Missing": "required feature or behavior is missing.",
            "UI_Layout": "layout, alignment, responsive display, spacing.",
            "UI_Label Message": "wrong text, label, message, translation.",
            "UI_Position Size": "position or size issue.",
            "DES_*": "design/spec/interface/table/data-flow related origin.",
            "DOC_*": "documentation/template/grammar issue.",
        },
    },
    "cause_category": {
        "summary": "Process/root cause category.",
        "default": "Not Applicable",
        "options": {
            "REQ_Missing or incomplete": "requirement missing/incomplete.",
            "REQ_Unclear Or Ambiguous": "requirement wording caused misunderstanding.",
            "DES_Missing or incomplete": "design missing/incomplete.",
            "FUN_Integration Problem": "integration between components caused the bug.",
            "DEP_Environment Issue": "environment caused or exposed the bug.",
            "DEP_Deployment Issue": "deployment/setup caused the bug.",
            "IMP_Insufficient analysis  before implementation": "missed case due to insufficient analysis.",
            "IMP_Shortage of time": "time pressure caused incomplete handling.",
            "IMP_Discipline/process non-compliance": "process skipped/not followed.",
            "SKI_*": "skill or knowledge gap.",
            "COM_Missing communication": "communication gap.",
            "CAR_Carelessness": "simple oversight, typo, missed check.",
            "PRO_Missing or incomplete": "process/procedure missing or incomplete.",
            "Not Applicable": "unknown or no clear process cause.",
        },
    },
}


def field_guidance(field=None, config=None, project_key=None, start_path=None):
    workflow = guidance_workflow(config, project_key, start_path=start_path)
    custom_fields = workflow.get("custom_fields", {})

    def get_val(key):
        return custom_default(custom_fields, key)

    if field is None:
        return {
            "fields": list(GUIDED_FIELDS),
            "defaults": {
                field_key: get_val(field_key)
                for field_key in GUIDED_FIELDS
            },
            "workflowManagedFields": list(WORKFLOW_MANAGED_FIELDS),
            "hint": "Only the listed fields have option guidance. Run `backlog.py bug fields <field>` for their details; inspect workflow-managed values in resolve dry-run.",
        }
    if field not in FIELD_GUIDANCE:
        available = ", ".join(FIELD_GUIDANCE.keys())
        raise ValueError(f"Unknown field '{field}'. Available: {available}")
    return {
        "field": field,
        **FIELD_GUIDANCE[field],
        "default": get_val(field),
    }
