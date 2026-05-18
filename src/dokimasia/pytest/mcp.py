from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dokimasia.core.model import McpCall

_MISSING = object()


def assert_mcp_called(
    result: Any,
    *,
    server: str,
    tool: str,
    times: int | None = None,
    min: int | None = None,
    max: int | None = None,
) -> None:
    """Assert that result.mcp_calls includes calls to the requested MCP server/tool."""
    if times is not None and (min is not None or max is not None):
        raise ValueError("times cannot be combined with min or max")

    calls = [normalize_mcp_call(call) for call in getattr(result, "mcp_calls", [])]
    matching_calls = [call for call in calls if call.server == server and call.tool == tool]
    actual = len(matching_calls)

    expected_lines = _expected_count_lines(times=times, min=min, max=max)
    if not expected_lines:
        expected_lines = ["expected count >= 1"]
        if actual >= 1:
            return
    elif _count_satisfies(actual, times=times, min=min, max=max):
        return

    label = f"{server}.{tool}"
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
    raise AssertionError("\n".join(lines))


def normalize_mcp_call(call: Any) -> McpCall:
    if isinstance(call, McpCall):
        return call

    server = _field(call, "server")
    tool = _field(call, "tool")
    if server in {_MISSING, None, ""}:
        raise ValueError("MCP call must include server")
    if tool in {_MISSING, None, ""}:
        raise ValueError("MCP call must include tool")

    arguments = _field(call, "arguments")
    if arguments is _MISSING or arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("MCP call arguments must be a dict")

    result = _field(call, "result")
    if result is _MISSING:
        result = None

    error = _normalize_error(_field(call, "error"))

    sequence = _field(call, "sequence")
    if sequence is _MISSING:
        sequence = None

    raw = _field(call, "raw")
    if raw is _MISSING:
        raw = call

    return McpCall(
        server=str(server),
        tool=str(tool),
        arguments=dict(arguments),
        result=result,
        error=error,
        sequence=None if sequence is None else int(sequence),
        raw=raw,
    )


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


def _format_mcp_call(call: McpCall) -> str:
    status = "error" if call.is_error else "ok"
    order = "" if call.sequence is None else f"#{call.sequence} "
    return f"{order}{call.server}.{call.tool} ({status})"


def _field(call: Any, name: str) -> Any:
    if isinstance(call, Mapping):
        return call.get(name, _MISSING)
    return getattr(call, name, _MISSING)


__all__ = [
    "assert_mcp_called",
    "normalize_mcp_call",
]
