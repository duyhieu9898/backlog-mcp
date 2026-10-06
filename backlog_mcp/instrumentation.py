"""FastMCP hooks that sit outside the tool bodies.

Both patch private or shared FastMCP internals (mcp>=1.27,<2), so they live here
and are covered by tests/test_instrumentation.py to fail loudly on an mcp upgrade.
"""

from typing import Any

from pydantic import ConfigDict, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase

from .arg_errors import describe_validation_error, format_arg_error
from .results import _error_result
from backlog_tool.telemetry import (
    record_arg_error,
    reset_client_arguments,
    set_client_arguments,
    start_call,
)


def forbid_unknown_tool_arguments() -> None:
    """Reject tool arguments that are not declared in the generated MCP schema.

    mcp<2 currently inherits Pydantic's extra="ignore" behavior for generated
    FastMCP argument models, which can silently discard misspelled or
    hallucinated fields. Configure the shared argument base before any tools are
    registered so generated schemas also advertise additionalProperties=false.
    """
    ArgModelBase.model_config = ConfigDict(
        **dict(ArgModelBase.model_config),
        extra="forbid",
    )

def record_rejected_tool_calls(mcp: FastMCP) -> None:
    """Log calls FastMCP rejects before the tool body runs.

    Argument validation (including extra="forbid") happens inside FastMCP, so a
    rejected call never reaches start_call and would be invisible in
    telemetry. Tool bodies catch their own errors, so any ToolError that
    escapes the manager is a rejection: invalid arguments or an unknown tool.

    The raw client arguments are also exposed to start_call so tool calls
    record what the client sent rather than every defaulted parameter.
    """
    manager = mcp._tool_manager
    call_tool = manager.call_tool

    async def call_tool_with_rejection_log(name, arguments, context=None, convert_result=False):
        token = set_client_arguments(arguments)
        try:
            return await call_tool(name, arguments, context=context, convert_result=convert_result)
        except ToolError as error:
            cause = error.__cause__
            status = "invalid_arguments" if isinstance(cause, ValidationError) else "rejected"
            start_call(name, arguments)
            if isinstance(cause, ValidationError):
                tool = manager.get_tool(name)
                valid = list((tool.parameters or {}).get("properties", {})) if tool else []
                details = describe_validation_error(cause, valid)
                record_arg_error(name, arguments, details)
                error = ToolError(format_arg_error(name, details, valid))
                error.__cause__ = cause
            _error_result(name, error, status=status)
            raise error
        finally:
            reset_client_arguments(token)

    manager.call_tool = call_tool_with_rejection_log
