"""MCP response shaping, pagination, and tool execution telemetry helpers."""

import time
from typing import Any

from mcp.types import CallToolResult, TextContent

from backlog_tool.settings import log_event, log_metric
from backlog_tool.telemetry import (
    clear_trace,
    client_metadata,
    ensure_trace,
    log_telemetry,
    serialized_bytes,
)


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
    started: float | None = None,
    dry_run: bool | None = None,
    project: str | None = None,
    status: str = "error",
) -> CallToolResult:
    message = str(error)
    text = f"Error: {message}"
    trace_id = ensure_trace(tool)
    text_bytes = len(text.encode("utf-8"))
    response_shape = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": None,
        "isError": True,
    }
    total_bytes = serialized_bytes(response_shape)
    if started is not None:
        duration_ms = (time.monotonic() - started) * 1000
        try:
            log_metric(
                tool,
                total_bytes,
                duration_ms,
                status,
                dry_run=dry_run,
                project=project,
                text_bytes=text_bytes,
                structured_bytes=0,
                total_response_bytes=total_bytes,
                trace_id=trace_id,
                client=client_metadata(),
            )
            log_telemetry(
                "tool_end",
                status=status,
                durationMs=round(duration_ms, 1),
                project=project,
                dryRun=dry_run,
                textBytes=text_bytes,
                structuredBytes=0,
                totalResponseBytes=total_bytes,
                estimatedTokens=round(total_bytes / 4),
                error=message,
            )
            log_event(
                "error",
                "tool_error",
                tool=tool,
                trace_id=trace_id,
                duration_ms=round(duration_ms, 1),
                error=message,
            )
        except Exception:
            pass
    clear_trace()

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
    started: float | None = None,
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
    trace_id = ensure_trace(tool)
    meta = {
        "tool": tool,
        "command": tool,
        "resourceUris": uris,
        "traceId": trace_id,
    }
    text_bytes = len(text.encode("utf-8"))
    structured_bytes = serialized_bytes(envelope_data)
    total_bytes = serialized_bytes(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": envelope_data,
            "_meta": meta,
            "isError": False,
        }
    )

    if started is not None:
        duration_ms = (time.monotonic() - started) * 1000
        try:
            log_metric(
                tool,
                total_bytes,
                duration_ms,
                "ok",
                dry_run=dry_run,
                project=project,
                text_bytes=text_bytes,
                structured_bytes=structured_bytes,
                total_response_bytes=total_bytes,
                item_count=returned,
                trace_id=trace_id,
                client=client_metadata(),
            )
            log_telemetry(
                "tool_end",
                status="ok",
                durationMs=round(duration_ms, 1),
                project=project,
                dryRun=dry_run,
                itemCount=returned,
                pagination=envelope_data.get("pagination"),
                textBytes=text_bytes,
                structuredBytes=structured_bytes,
                totalResponseBytes=total_bytes,
                estimatedTokens=round(total_bytes / 4),
            )
            log_event(
                "info",
                "tool_done",
                tool=tool,
                trace_id=trace_id,
                duration_ms=round(duration_ms, 1),
                status="ok",
                total_response_bytes=total_bytes,
            )
        except Exception:
            pass
    clear_trace()

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=envelope_data,
        _meta=meta,
    )


def _partial_write_result(
    tool: str,
    message: str,
    data: dict[str, Any],
    started: float | None = None,
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
    trace_id = ensure_trace(tool)
    meta = {"tool": tool, "command": tool, "traceId": trace_id}
    text_bytes = len(text.encode("utf-8"))
    structured_bytes = serialized_bytes(structured)
    total_bytes = serialized_bytes(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "_meta": meta,
            "isError": True,
        }
    )
    if started is not None:
        duration_ms = (time.monotonic() - started) * 1000
        try:
            log_metric(
                tool,
                total_bytes,
                duration_ms,
                "partial_write",
                dry_run=False,
                project=project,
                text_bytes=text_bytes,
                structured_bytes=structured_bytes,
                total_response_bytes=total_bytes,
                trace_id=trace_id,
                client=client_metadata(),
            )
            log_telemetry(
                "tool_end",
                status="partial_write",
                durationMs=round(duration_ms, 1),
                project=project,
                dryRun=False,
                textBytes=text_bytes,
                structuredBytes=structured_bytes,
                totalResponseBytes=total_bytes,
                estimatedTokens=round(total_bytes / 4),
                partialWrite=data,
            )
            log_event(
                "error",
                "tool_partial_write",
                tool=tool,
                trace_id=trace_id,
                duration_ms=round(duration_ms, 1),
                project=project,
            )
        except Exception:
            pass
    clear_trace()

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=True,
        _meta=meta,
    )
