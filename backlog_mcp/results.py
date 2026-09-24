"""MCP response shaping, pagination, and tool execution telemetry helpers."""

from typing import Any

from mcp.types import CallToolResult, TextContent

from backlog_tool.telemetry import current_trace_id, finish_call, serialized_bytes


def _to_markdown(data: Any, tool_name: str) -> str:
    if not data:
        return "No data."

    if isinstance(data, list):
        count = len(data)
        summary = f"Retrieved {count} items via '{tool_name}'."
        if count > 0:
            lines = [summary, ""]
            for item in data:
                if isinstance(item, dict):
                    key = item.get("issueKey") or item.get("key") or ""
                    title = item.get("summary") or ""
                    status = item.get("status") or ""
                    status_suffix = f" [{status}]" if status else ""
                    lines.append(f"- **{key}**: {title}{status_suffix}")
            lines.append("\nFull details are available in the structured content.")
            return "\n".join(lines)
        return summary

    if isinstance(data, dict):
        key = data.get("issueKey") or data.get("key")
        title = data.get("summary")
        status = data.get("status")
        if key and title:
            status_suffix = f" [{status}]" if status else ""
            return f"Retrieved item **{key}**: {title}{status_suffix}.\nFull details are available in the structured content."
        lines = [f"Result of '{tool_name}':", ""]
        for key_name, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"- **{key_name}**: (structured data)")
            else:
                lines.append(f"- **{key_name}**: {value}")
        return "\n".join(lines)

    return str(data)


def _resource_uris(data: Any) -> list[str]:
    items = data if isinstance(data, list) else [data]
    uris = []
    for item in items:
        if isinstance(item, dict):
            issue_key = item.get("issueKey") or item.get("issue")
            if issue_key:
                uris.append(f"backlog://issue/{issue_key}")
    return sorted(set(uris))


def _pagination(limit: int, offset: int, returned: int, enabled: bool) -> dict[str, Any]:
    has_more = bool(enabled and limit > 0 and returned >= limit)
    next_cursor = str(offset + returned) if has_more else None
    return {
        "limit": limit if enabled else 0,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


def _parse_cursor(cursor: str) -> int:
    if not cursor:
        return 0
    try:
        offset = int(cursor)
        if offset < 0:
            raise ValueError("Cursor (offset) must be a non-negative integer.")
        return offset
    except ValueError:
        raise ValueError(
            f"Invalid cursor format: '{cursor}'. Cursor must be a non-negative integer string representing the offset (e.g., '50')."
        )


def _error_result(
    tool: str,
    error: Exception,
    dry_run: bool | None = None,
    project: str | None = None,
    status: str = "error",
) -> CallToolResult:
    message = str(error)
    text = f"Error: {message}"
    response_shape = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": None,
        "isError": True,
    }
    total_bytes = serialized_bytes(response_shape)

    trace_id = current_trace_id() or ""
    finish_call(
        status,
        result=None,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode=None if dry_run is None else ("preview" if dry_run else "apply"),
        error=message,
    )

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=None,
        isError=True,
        _meta={"tool": tool, "command": tool, "traceId": trace_id},
    )


def _build_result(
    data: Any,
    tool: str,
    list_key: str | None = None,
    limit: int = 0,
    offset: int = 0,
    paginated: bool = False,
    dry_run: bool | None = None,
    project: str | None = None,
) -> CallToolResult:
    text = _to_markdown(data, tool)
    result_data = {list_key or "items": data} if isinstance(data, list) else data
    returned = len(data) if isinstance(data, list) else (0 if data in (None, "", [], {}) else 1)

    envelope_data = {
        "ok": True,
        "data": result_data if result_data is not None else {},
    }
    if paginated:
        envelope_data["pagination"] = _pagination(limit, offset, returned, paginated)

    uris = _resource_uris(data)
    trace_id = current_trace_id() or ""
    meta = {
        "tool": tool,
        "command": tool,
        "resourceUris": uris,
        "traceId": trace_id,
    }
    total_bytes = serialized_bytes(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": envelope_data,
            "_meta": meta,
            "isError": False,
        }
    )

    finish_call(
        "ok",
        result=envelope_data,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode=None if dry_run is None else ("preview" if dry_run else "apply"),
    )

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=envelope_data,
        _meta=meta,
    )


def _partial_write_result(
    tool: str,
    message: str,
    data: dict[str, Any],
    project: str | None = None,
) -> CallToolResult:
    """Return a machine-readable error when a multi-step mutation partially commits."""
    text = f"Partial write: {message}"
    structured = {
        "ok": False,
        "error": {
            "kind": "partial_write",
            "message": message,
            **data,
        },
    }
    trace_id = current_trace_id() or ""
    meta = {"tool": tool, "command": tool, "traceId": trace_id}
    total_bytes = serialized_bytes(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "_meta": meta,
            "isError": True,
        }
    )

    finish_call(
        "partial_write",
        result=structured,
        text=text,
        response_bytes=total_bytes,
        project_key=project,
        mode="apply",
        error=message,
    )

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=True,
        _meta=meta,
    )
