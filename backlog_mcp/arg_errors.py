"""Turn FastMCP/pydantic argument validation errors into loggable, model-friendly details."""

import difflib


def _normalize(name):
    return str(name).replace("_", "").replace("-", "").lower()


def _suggest(unknown, valid_params):
    by_norm = {_normalize(name): name for name in valid_params}
    suggestions = {}
    for name in unknown:
        norm = _normalize(name)
        if norm in by_norm:
            suggestions[name] = by_norm[norm]
            continue
        match = difflib.get_close_matches(norm, list(by_norm), n=1, cutoff=0.6)
        if match:
            suggestions[name] = by_norm[match[0]]
    return suggestions


def describe_validation_error(error, valid_params):
    unknown, missing, invalid = [], [], []
    for item in error.errors():
        name = str(item["loc"][0]) if item.get("loc") else ""
        kind = item.get("type", "")
        if kind == "extra_forbidden":
            unknown.append(name)
        elif kind == "missing":
            missing.append(name)
        else:
            invalid.append({"name": name, "reason": kind})
    return {
        "unknown": unknown,
        "missingRequired": missing,
        "invalid": invalid,
        "suggested": _suggest(unknown, valid_params),
    }


def format_arg_error(tool, details, valid_params):
    parts = []
    for name in details.get("unknown") or []:
        hint = details.get("suggested", {}).get(name)
        parts.append(f"unknown '{name}'" + (f" (did you mean '{hint}'?)" if hint else ""))
    parts += [f"missing required '{name}'" for name in details.get("missingRequired") or []]
    parts += [f"invalid '{item['name']}' ({item['reason']})" for item in details.get("invalid") or []]
    return f"Invalid arguments for {tool}: {'; '.join(parts)}. Valid parameters: {', '.join(valid_params)}"
