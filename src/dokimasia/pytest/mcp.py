from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from dokimasia.core.model import McpCall
from dokimasia.core.json import decode_nested_json_strings

McpSuccessFilter = Literal["success", "failure", "any"]
McpPredicate = Callable[[McpCall], bool]

_MISSING = object()


def assert_mcp_called(
    result: Any,
    *,
    server: str | None = None,
    tool: str | None = None,
    mode: str | None = "call",
    success: bool | McpSuccessFilter | None = None,
    where: McpPredicate | None = None,
    times: int | None = None,
    min: int | None = None,
    max: int | None = None,
) -> None:
    """Assert that result.mcp_calls includes MCP evidence matching the filters."""

    _assert_mcp_count(
        result,
        server=server,
        tool=tool,
        mode=mode,
        success=success,
        where=where,
        times=times,
        min=min,
        max=max,
    )


def assert_mcp_not_called(
    result: Any,
    *,
    server: str | None = None,
    tool: str | None = None,
    mode: str | None = "call",
    success: bool | McpSuccessFilter | None = None,
    where: McpPredicate | None = None,
) -> None:
    """Assert that result.mcp_calls has no MCP evidence matching the filters."""

    _assert_mcp_count(
        result,
        server=server,
        tool=tool,
        mode=mode,
        success=success,
        where=where,
        times=0,
        min=None,
        max=None,
    )


def normalize_mcp_call(call: Any) -> McpCall:
    mode = _field(call, "mode")
    if mode in {_MISSING, None, ""}:
        mode = "call"

    server = _field(call, "server")
    if server in {_MISSING, None, ""}:
        server = None

    tool = _field(call, "tool")
    if tool in {_MISSING, None, ""}:
        tool = None

    arguments = _field(call, "arguments")
    if arguments is _MISSING or arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("MCP call arguments must be a dict")
    arguments = decode_nested_json_strings(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("MCP call arguments must decode to a dict")

    result = _field(call, "result")
    if result is _MISSING:
        result = None

    error = _normalize_error(_field(call, "error"))
    is_error = _field(call, "is_error")
    if is_error is _MISSING:
        is_error = _field(call, "isError")
    if error is None and is_error is True:
        error = "MCP operation failed"

    sequence = _field(call, "sequence")
    if sequence is _MISSING:
        sequence = None

    call_id = _field(call, "call_id")
    if call_id in {_MISSING, None, ""}:
        call_id = None

    raw = _field(call, "raw")
    if raw is _MISSING:
        raw = call

    return McpCall(
        server=None if server is None else str(server),
        tool=None if tool is None else str(tool),
        mode=str(mode),
        arguments=dict(arguments),
        result=result,
        error=error,
        sequence=None if sequence is None else int(sequence),
        call_id=None if call_id is None else str(call_id),
        raw=raw,
    )


def _assert_mcp_count(
    result: Any,
    *,
    server: str | None,
    tool: str | None,
    mode: str | None,
    success: bool | McpSuccessFilter | None,
    where: McpPredicate | None,
    times: int | None,
    min: int | None,
    max: int | None,
) -> None:
    if times is not None and (min is not None or max is not None):
        raise ValueError("times cannot be combined with min or max")

    success_filter = _normalize_success_filter(success)
    calls = [normalize_mcp_call(call) for call in getattr(result, "mcp_calls", [])]
    matching_calls = [
        call
        for call in calls
        if _mcp_call_matches(call, server=server, tool=tool, mode=mode, success=success_filter, where=where)
    ]
    actual = len(matching_calls)

    expected_lines = _expected_count_lines(times=times, min=min, max=max)
    if not expected_lines:
        expected_lines = ["expected count >= 1"]
        if actual >= 1:
            return
    elif _count_satisfies(actual, times=times, min=min, max=max):
        return

    raise AssertionError(_mcp_assertion_message(server, tool, mode, success_filter, expected_lines, actual, calls))


def _mcp_call_matches(
    call: McpCall,
    *,
    server: str | None,
    tool: str | None,
    mode: str | None,
    success: McpSuccessFilter,
    where: McpPredicate | None,
) -> bool:
    if server is not None and call.server != server:
        return False
    if tool is not None and call.tool != tool:
        return False
    if mode is not None and call.mode != mode:
        return False
    if success == "success" and call.is_error:
        return False
    if success == "failure" and not call.is_error:
        return False
    if where is not None and not where(call):
        return False
    return True


def _normalize_success_filter(success: bool | McpSuccessFilter | None) -> McpSuccessFilter:
    if success is None or success == "any":
        return "any"
    if success is True or success == "success":
        return "success"
    if success is False or success == "failure":
        return "failure"
    raise ValueError("success must be one of: True, False, 'success', 'failure', 'any', or None")


def _normalize_error(error: Any) -> str | None:
    if error is _MISSING or error is None:
        return None
    text = str(error).strip()
    return text or None


def _expected_count_lines(*, times: int | None, min: int | None, max: int | None) -> list[str]:
    if times is not None:
        return [f"expected count == {times}"]

    lines: list[str] = []
    if min is not None:
        lines.append(f"expected count >= {min}")
    if max is not None:
        lines.append(f"expected count <= {max}")
    return lines


def _count_satisfies(actual: int, *, times: int | None, min: int | None, max: int | None) -> bool:
    if times is not None:
        return actual == times
    if min is not None and actual < min:
        return False
    if max is not None and actual > max:
        return False
    return True


def _mcp_assertion_message(
    server: str | None,
    tool: str | None,
    mode: str | None,
    success: McpSuccessFilter,
    expected_lines: list[str],
    actual: int,
    calls: list[McpCall],
) -> str:
    label = _mcp_assertion_label(server, tool, mode, success)
    lines = [
        f"MCP call assertion failed for {label}",
        *expected_lines,
        f"actual count {actual}",
        "observed MCP calls:",
    ]
    if calls:
        lines.extend(f"- {_format_mcp_call(call)}" for call in calls)
    else:
        lines.append("- <none>")
    return "\n".join(lines)


def _mcp_assertion_label(server: str | None, tool: str | None, mode: str | None, success: McpSuccessFilter) -> str:
    target = ".".join(part for part in (server, tool) if part is not None) or "*"
    filters = []
    if mode is not None:
        filters.append(f"mode={mode}")
    if success != "any":
        filters.append(f"success={success}")
    if filters:
        return f"{target} ({', '.join(filters)})"
    return target


def _format_mcp_call(call: McpCall) -> str:
    status = "error" if call.is_error else "ok"
    order = "" if call.sequence is None else f"#{call.sequence} "
    target = ".".join(part for part in (call.server, call.tool) if part is not None) or "<unknown>"
    parts = [f"{order}{target} mode={call.mode} ({status})"]
    if call.arguments:
        parts.append(f"arguments={call.arguments!r}")
    if call.error:
        parts.append(f"error={call.error!r}")
    return " ".join(parts)


def _field(call: Any, name: str) -> Any:
    if isinstance(call, Mapping):
        return call.get(name, _MISSING)
    return getattr(call, name, _MISSING)


__all__ = [
    "assert_mcp_called",
    "assert_mcp_not_called",
    "normalize_mcp_call",
]
