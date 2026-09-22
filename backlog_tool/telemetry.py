"""Vendor-neutral tracing and telemetry for MCP/tool/API execution."""

import json
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from . import settings

SCHEMA_VERSION = 2
_trace_id: ContextVar[str | None] = ContextVar("backlog_mcp_trace_id", default=None)
_tool_name: ContextVar[str | None] = ContextVar("backlog_mcp_tool_name", default=None)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _jsonable(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _mcp_client_info():
    """clientInfo the MCP client sent in initialize, when inside an MCP request."""
    try:
        from mcp.server.lowlevel.server import request_ctx

        params = request_ctx.get().session.client_params
    except Exception:
        return None
    return getattr(params, "clientInfo", None)


def client_metadata():
    info = _mcp_client_info()
    return {
        "name": os.environ.get("BACKLOG_MCP_CLIENT") or getattr(info, "name", None) or "unknown",
        "version": os.environ.get("BACKLOG_MCP_CLIENT_VERSION") or getattr(info, "version", None),
        "transport": os.environ.get("BACKLOG_MCP_TRANSPORT", "stdio"),
    }


def current_trace_id():
    return _trace_id.get()


def current_tool_name():
    return _tool_name.get()


def ensure_trace(tool: str | None = None):
    trace_id = _trace_id.get()
    if trace_id is None:
        trace_id = uuid.uuid4().hex
        _trace_id.set(trace_id)
    if tool:
        _tool_name.set(tool)
    return trace_id


def begin_tool_trace(tool: str, arguments: dict[str, Any] | None = None):
    trace_id = uuid.uuid4().hex
    _trace_id.set(trace_id)
    _tool_name.set(tool)
    args = {
        k: _jsonable(v)
        for k, v in (arguments or {}).items()
        if k not in {"started", "trace_id"}
    }
    log_telemetry("tool_start", tool=tool, arguments=args)
    return trace_id


def clear_trace():
    _trace_id.set(None)
    _tool_name.set(None)


def log_telemetry(event: str, **fields):
    try:
        path = getattr(
            settings,
            "TELEMETRY_PATH",
            os.path.join(settings.LOG_DIR, "telemetry.jsonl"),
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        settings.rotate_file_if_needed(path, max_bytes=20 * 1024 * 1024, backup_count=5)
        record = {
            "schemaVersion": SCHEMA_VERSION,
            "ts": _now(),
            "event": event,
            "traceId": ensure_trace(),
            "tool": current_tool_name(),
            "client": client_metadata(),
            **{k: _jsonable(v) for k, v in fields.items() if v is not None},
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def serialized_bytes(value: Any):
    return len(
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
