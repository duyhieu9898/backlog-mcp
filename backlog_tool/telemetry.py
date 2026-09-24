"""Structured local telemetry for the Backlog MCP server and CLI.

Layout (see docs/telemetry.md): calls.jsonl (index, one line per tool call),
errors.jsonl, sessions.jsonl, details/<YYYY-MM-DD>.jsonl (arguments, result,
API calls, mutation), all linked by traceId.
"""

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import settings

SCHEMA_VERSION = 3
SESSION_ID = uuid.uuid4().hex
LARGE_RESPONSE_BYTES = 8192
ERROR_BODY_LIMIT = 2048
DETAILS_RETENTION_DAYS = 30
INDEX_MAX_BYTES = 20 * 1024 * 1024
INDEX_BACKUPS = 5
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


@dataclass
class _Call:
    trace_id: str
    tool: str
    arguments: dict
    started: float
    api: list = field(default_factory=list)
    mutation: dict | None = None


_call: ContextVar[_Call | None] = ContextVar("backlog_telemetry_call", default=None)
_client_arguments: ContextVar[dict | None] = ContextVar("backlog_telemetry_client_arguments", default=None)
_surface: ContextVar[str] = ContextVar("backlog_telemetry_surface", default="mcp")
_eval_tags: dict[str, str] = {}


def log_paths():
    log_dir = settings.LOG_DIR
    return {
        "calls": os.path.join(log_dir, "calls.jsonl"),
        "errors": os.path.join(log_dir, "errors.jsonl"),
        "sessions": os.path.join(log_dir, "sessions.jsonl"),
        "details_dir": os.path.join(log_dir, "details"),
    }


def set_surface(surface):
    _surface.set(surface)


def set_eval_tags(run_id, scenario):
    _eval_tags.clear()
    if run_id:
        _eval_tags["runId"] = run_id
    if scenario:
        _eval_tags["scenario"] = scenario


def set_client_arguments(arguments):
    """Remember the arguments exactly as the MCP client sent them."""
    return _client_arguments.set(dict(arguments or {}))


def reset_client_arguments(token):
    _client_arguments.reset(token)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _jsonable(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [_jsonable(v) for v in items]
    return str(value)


def serialized_bytes(value):
    return len(json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _mcp_client_info():
    try:
        from mcp.server.lowlevel.server import request_ctx

        return getattr(request_ctx.get().session.client_params, "clientInfo", None)
    except Exception:
        return None


def client_metadata():
    info = _mcp_client_info()
    return {
        "name": os.environ.get("BACKLOG_MCP_CLIENT") or getattr(info, "name", None) or "unknown",
        "version": os.environ.get("BACKLOG_MCP_CLIENT_VERSION") or getattr(info, "version", None),
    }


def _common():
    return {
        "v": SCHEMA_VERSION,
        "ts": _now(),
        "sessionId": SESSION_ID,
        "surface": _surface.get(),
        "client": client_metadata(),
        **_eval_tags,
    }


def _append(path, record, *, rotate=True):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if rotate:
            settings.rotate_file_if_needed(path, max_bytes=INDEX_MAX_BYTES, backup_count=INDEX_BACKUPS)
        line = json.dumps({k: v for k, v in record.items() if v is not None}, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as error:
        settings.report_log_failure(path, error)


def _issue_from(arguments):
    for key in ("issue_key", "issue_ref", "issue_id", "parent_key"):
        value = arguments.get(key)
        if isinstance(value, str) and ISSUE_KEY_RE.match(value):
            return value
    return None


def start_call(tool, arguments=None):
    client_arguments = _client_arguments.get()
    source = client_arguments if client_arguments is not None else (arguments or {})
    args = {k: _jsonable(v) for k, v in source.items() if k not in {"started", "trace_id"}}
    call = _Call(uuid.uuid4().hex, tool, args, time.monotonic())
    _call.set(call)
    return call.trace_id


def current_trace_id():
    call = _call.get()
    return call.trace_id if call else None


def current_tool():
    call = _call.get()
    return call.tool if call else None


def record_api_call(method, path, status, ok, duration_ms, request_bytes, response_bytes, body):
    keep_body = os.environ.get("BACKLOG_MCP_LOG_BODIES") == "full" or not ok or method != "GET"
    entry = {
        "method": method,
        "path": path,
        "status": status,
        "durationMs": round(duration_ms, 1),
        "requestBytes": request_bytes,
        "responseBytes": response_bytes,
    }
    if keep_body:
        entry["body"] = body
    call = _call.get()
    if call is not None:
        call.api.append(entry)
    if not ok:
        record_error(
            "api_error",
            f"{method} {path} -> {status}",
            method=method,
            path=path,
            status=status,
            body=(body or "")[:ERROR_BODY_LIMIT],
        )


def record_mutation(**fields):
    call = _call.get()
    if call is not None:
        call.mutation = {k: _jsonable(v) for k, v in fields.items() if v is not None}


def record_error(kind, message, **fields):
    call = _call.get()
    record = {
        **_common(),
        "traceId": call.trace_id if call else None,
        "kind": kind,
        "tool": fields.pop("tool", None) or (call.tool if call else None),
        "message": message,
        **{k: _jsonable(v) for k, v in fields.items()},
    }
    _append(log_paths()["errors"], record)


def record_arg_error(tool, arguments, details):
    record_error(
        "arg_error",
        "invalid tool arguments",
        tool=tool,
        sent=sorted((arguments or {}).keys()),
        unknown=details.get("unknown", []),
        missingRequired=details.get("missingRequired", []),
        invalid=details.get("invalid", []),
        suggested=details.get("suggested", {}),
    )


def plan_hash(issue, payload):
    canonical = json.dumps(
        {"issue": issue, "payload": _jsonable(payload)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def finish_call(status, *, result=None, text=None, response_bytes=0, project_key=None, issue_key=None, mode=None, error=None):
    call = _call.get()
    if call is None:
        return None
    try:
        if status == "error":
            record_error("tool_error", error or "")
        elif status == "partial_write":
            record_error("partial_write", error or "")
        paths = log_paths()
        issue = issue_key or _issue_from(call.arguments)
        project = project_key or (issue.rsplit("-", 1)[0] if issue else None) or call.arguments.get("project_key") or None
        _append(paths["calls"], {
            **_common(),
            "traceId": call.trace_id,
            "tool": call.tool,
            "argKeys": sorted(call.arguments),
            "issueKey": issue,
            "projectKey": project,
            "mode": mode or call.arguments.get("mode"),
            "status": status,
            "durationMs": round((time.monotonic() - call.started) * 1000, 1),
            "apiCalls": len(call.api),
            "apiMs": round(sum(a["durationMs"] for a in call.api), 1),
            "responseBytes": response_bytes,
            "estTokens": round(response_bytes / 4),
            "flags": ["large_response"] if response_bytes > LARGE_RESPONSE_BYTES else [],
        })
        detail_path = os.path.join(paths["details_dir"], f"{date.today().isoformat()}.jsonl")
        _append(detail_path, {
            **_common(),
            "traceId": call.trace_id,
            "tool": call.tool,
            "arguments": call.arguments,
            "result": _jsonable(result),
            "text": text,
            "api": call.api,
            "mutation": call.mutation,
        }, rotate=False)
        return call.trace_id
    finally:
        _call.set(None)


def _git(*args):
    return subprocess.run(
        ["git", "-C", settings.MCP_ROOT, *args],
        capture_output=True, text=True, timeout=2,
    ).stdout.strip()


def server_version():
    try:
        git_sha = _git("rev-parse", "--short", "HEAD") or None
        dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    except Exception:
        git_sha, dirty = None, None
    try:
        version = importlib.metadata.version("hieund-backlog-mcp")
    except Exception:
        version = None
    return {"version": version, "gitSha": git_sha, "dirty": dirty}


def _purge_old_details():
    folder = log_paths()["details_dir"]
    cutoff = (date.today() - timedelta(days=DETAILS_RETENTION_DAYS)).isoformat()
    try:
        for name in os.listdir(folder):
            if name.endswith(".jsonl") and name[:10] < cutoff:
                os.remove(os.path.join(folder, name))
    except FileNotFoundError:
        return
    except Exception as error:
        settings.report_log_failure(folder, error)


def log_session_start(*, backend="real", workspace=None, tool_count=None):
    version = server_version()
    _append(log_paths()["sessions"], {
        **_common(),
        "event": "session_start",
        "pid": os.getpid(),
        "version": version["version"],
        "gitSha": version["gitSha"],
        "dirty": version["dirty"],
        "toolCount": tool_count,
        "backend": backend,
        "workspace": workspace,
    })
    _purge_old_details()
