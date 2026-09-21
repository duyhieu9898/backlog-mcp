from typing import Any


def _option_index(items: list[dict[str, Any]]) -> dict[int, str | None]:
    return {
        int(item["id"]): item.get("name")
        for item in items
        if item.get("id") is not None
    }


def _compare_options(local_items, live_items):
    local = _option_index(local_items or [])
    live = _option_index(live_items or [])
    added = [
        {"id": option_id, "name": live[option_id]}
        for option_id in sorted(live.keys() - local.keys())
    ]
    removed = [
        {"id": option_id, "name": local[option_id]}
        for option_id in sorted(local.keys() - live.keys())
    ]
    renamed = [
        {
            "id": option_id,
            "localName": local[option_id],
            "liveName": live[option_id],
        }
        for option_id in sorted(local.keys() & live.keys())
        if local[option_id] != live[option_id]
    ]
    return {
        "changed": bool(added or removed or renamed),
        "added": added,
        "removed": removed,
        "renamed": renamed,
    }


def _field_by_wire_name(fields):
    return {
        config.get("field"): (key, config)
        for key, config in (fields or {}).items()
        if config.get("field")
    }


def compare_project_catalog(local: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    """Compare cached catalog semantics with a freshly fetched project config."""
    local_bug = local.get("bug", {})
    live_bug = live.get("bug", {})

    sections = {
        "issueTypes": _compare_options(
            local_bug.get("issue_type_options"),
            live_bug.get("issue_type_options"),
        ),
        "statuses": _compare_options(
            local_bug.get("status_options"),
            live_bug.get("status_options"),
        ),
        "categories": _compare_options(
            local_bug.get("category_options"),
            live_bug.get("category_options"),
        ),
    }

    local_fields = _field_by_wire_name(local_bug.get("custom_fields"))
    live_fields = _field_by_wire_name(live_bug.get("custom_fields"))

    added_fields = []
    removed_fields = []
    changed_fields = []
    for wire_name in sorted(live_fields.keys() - local_fields.keys()):
        key, config = live_fields[wire_name]
        added_fields.append(
            {"field": wire_name, "key": key, "label": config.get("label")}
        )
    for wire_name in sorted(local_fields.keys() - live_fields.keys()):
        key, config = local_fields[wire_name]
        removed_fields.append(
            {"field": wire_name, "key": key, "label": config.get("label")}
        )
    for wire_name in sorted(local_fields.keys() & live_fields.keys()):
        local_key, local_config = local_fields[wire_name]
        live_key, live_config = live_fields[wire_name]
        option_diff = _compare_options(
            local_config.get("value_options"),
            live_config.get("value_options"),
        )
        if (
            local_key != live_key
            or local_config.get("label") != live_config.get("label")
            or option_diff["changed"]
        ):
            changed_fields.append(
                {
                    "field": wire_name,
                    "localKey": local_key,
                    "liveKey": live_key,
                    "localLabel": local_config.get("label"),
                    "liveLabel": live_config.get("label"),
                    "options": option_diff,
                }
            )

    custom_fields = {
        "changed": bool(added_fields or removed_fields or changed_fields),
        "added": added_fields,
        "removed": removed_fields,
        "changedFields": changed_fields,
    }
    changed = any(section["changed"] for section in sections.values()) or custom_fields["changed"]

    return {
        "project": local.get("key") or live.get("key"),
        "changed": changed,
        "projectIdentity": {
            "changed": (
                local.get("id") != live.get("id")
                or local.get("name") != live.get("name")
                or local.get("key") != live.get("key")
            ),
            "local": {
                "id": local.get("id"),
                "key": local.get("key"),
                "name": local.get("name"),
            },
            "live": {
                "id": live.get("id"),
                "key": live.get("key"),
                "name": live.get("name"),
            },
        },
        **sections,
        "customFields": custom_fields,
    }
