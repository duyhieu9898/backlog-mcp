#!/usr/bin/env python3
from .settings import resolve_user_id


def find_option(options, selected, label):
    if selected is None:
        return None
    selected_text = str(selected)
    if selected_text.isdigit():
        return int(selected_text)

    for option in options:
        if option.get("name") == selected:
            return option.get("id")
    # Case-insensitive fallback
    for option in options:
        if str(option.get("name")).lower() == selected_text.lower():
            return option.get("id")
    available = ", ".join(str(option.get("name")) for option in options)
    raise ValueError(f"Unknown {label} '{selected}'. Available: {available}")


def issue_type_options(project):
    bug = project.get("bug", {})
    return bug.get("_issue_type_options", bug.get("issue_type_options", []))


def category_options(project):
    bug = project.get("bug", {})
    return bug.get("_category_options", bug.get("category_options", []))


def status_options(project):
    bug = project.get("bug", {})
    return bug.get("_status_options", bug.get("status_options", []))


def resolve_assignee(config, selected):
    if selected is None:
        return None
    if str(selected).isdigit():
        return int(selected)
    return resolve_user_id(config, selected)


def resolve_issue_type(project, selected):
    return find_option(issue_type_options(project), selected, "issue type")


def resolve_category(project, selected):
    return find_option(category_options(project), selected, "category")


def resolve_status(project, selected):
    return find_option(status_options(project), selected, "status")


def parse_custom_args(custom_args):
    values = {}
    for item in custom_args or []:
        if "=" not in item:
            raise ValueError(f"Invalid custom field '{item}'. Use key=value.")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_custom_field_value(field_config, selected_value):
    if selected_value is None:
        return None
    options = field_config.get("value_options", [])
    if not options:
        return selected_value
    return find_option(options, selected_value, field_config.get("label") or field_config.get("field"))


def resolve_custom_fields(project, custom_args):
    payload = {}
    fields = project.get("bug", {}).get("custom_fields", {})
    parsed = parse_custom_args(custom_args)
    for key, selected in parsed.items():
        field = fields.get(key)
        if not field:
            available = ", ".join(sorted(fields.keys()))
            raise ValueError(f"Unknown custom field '{key}'. Available: {available}")
        value = resolve_custom_field_value(field, selected)
        if value is not None:
            payload[field["field"]] = value
    return payload


def resolve_custom_field_defaults(project, selections):
    payload = {}
    fields = project.get("bug", {}).get("custom_fields", {})
    for field_key, selected_value in selections.items():
        field_config = fields.get(field_key)
        if not field_config:
            available = ", ".join(sorted(fields.keys()))
            raise ValueError(f"Unknown custom field '{field_key}'. Available: {available}")
        value = resolve_custom_field_value(field_config, selected_value)
        if value is not None:
            payload[field_config["field"]] = value
    return payload
