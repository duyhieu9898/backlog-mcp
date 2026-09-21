#!/usr/bin/env python3
"""Build and write a project catalog from the Backlog API."""
import json
import os
import re

from .client import BacklogClient
from .settings import PROJECTS_CONFIG_DIR


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "custom_field"


def option_summary(items):
    return [{"id": item.get("id"), "name": item.get("name")} for item in items]


def custom_field_value_options(custom_field):
    items = custom_field.get("items")
    if isinstance(items, list):
        return option_summary(items)
    return []


def custom_field_entry(custom_field):
    entry = {
        "label": custom_field.get("name"),
        "field": f"customField_{custom_field.get('id')}",
    }
    options = custom_field_value_options(custom_field)
    if options:
        entry["value_options"] = options
    return entry


def build_project_config(config, project_key):
    client = BacklogClient(config)
    project = client.request_json("GET", f"/projects/{project_key}")
    issue_types = client.request_json("GET", f"/projects/{project_key}/issueTypes")
    categories = client.request_json("GET", f"/projects/{project_key}/categories")
    statuses = client.request_json("GET", f"/projects/{project_key}/statuses")
    custom_fields = client.request_json("GET", f"/projects/{project_key}/customFields")

    custom_field_config = {}
    for custom_field in custom_fields:
        key = slugify(custom_field.get("name") or f"custom_field_{custom_field.get('id')}")
        if key in custom_field_config:
            key = f"{key}_{custom_field.get('id')}"
        custom_field_config[key] = custom_field_entry(custom_field)

    return {
        "key": project.get("projectKey") or project_key,
        "name": project.get("name"),
        "id": project.get("id"),
        "bug": {
            "category_options": option_summary(categories),
            "issue_type_options": option_summary(issue_types),
            "status_options": option_summary(statuses),
            "custom_fields": custom_field_config,
        },
    }


def write_catalog(project_config):
    os.makedirs(PROJECTS_CONFIG_DIR, exist_ok=True)
    path = os.path.join(PROJECTS_CONFIG_DIR, f"{project_config['key']}.json")
    with open(path, "w", encoding="utf-8") as output_file:
        output_file.write(json.dumps(project_config, indent=2, ensure_ascii=False) + "\n")
    return path
