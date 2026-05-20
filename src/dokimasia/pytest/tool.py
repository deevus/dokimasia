from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dokimasia.core.model import TraceEvent

ToolPredicate = Callable[[TraceEvent], bool]


def tool_calls(result: Any, tool: str | None = None, *, where: ToolPredicate | None = None) -> list[TraceEvent]:
    """Return generic agent tool-call trace events matching the filters."""

    calls = [event for event in getattr(result, "trace_events", []) if event.kind == "tool.call"]
    return [event for event in calls if _tool_call_matches(event, tool=tool, where=where)]


def assert_tool_called(
    result: Any,
    *,
    tool: str | None = None,
    where: ToolPredicate | None = None,
    times: int | None = None,
    min: int | None = None,
    max: int | None = None,
) -> None:
    """Assert that result.trace_events includes generic agent tool-call evidence matching the filters."""

    _assert_tool_count(result, tool=tool, where=where, times=times, min=min, max=max)


def assert_tool_not_called(
    result: Any,
    *,
    tool: str | None = None,
    where: ToolPredicate | None = None,
) -> None:
    """Assert that result.trace_events has no generic agent tool-call evidence matching the filters."""

    _assert_tool_count(result, tool=tool, where=where, times=0, min=None, max=None)


def _assert_tool_count(
    result: Any,
    *,
    tool: str | None,
    where: ToolPredicate | None,
    times: int | None,
    min: int | None,
    max: int | None,
) -> None:
    if times is not None and (min is not None or max is not None):
        raise ValueError("times cannot be combined with min or max")

    calls = [event for event in getattr(result, "trace_events", []) if event.kind == "tool.call"]
    matching_calls = [event for event in calls if _tool_call_matches(event, tool=tool, where=where)]
    actual = len(matching_calls)

    expected_lines = _expected_count_lines(times=times, min=min, max=max)
    if not expected_lines:
        expected_lines = ["expected count >= 1"]
        if actual >= 1:
            return
    elif _count_satisfies(actual, times=times, min=min, max=max):
        return

    raise AssertionError(_tool_assertion_message(tool, expected_lines, actual, calls))


def _tool_call_matches(event: TraceEvent, *, tool: str | None, where: ToolPredicate | None) -> bool:
    if tool is not None and event.tool != tool:
        return False
    if where is not None and not where(event):
        return False
    return True


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


def _tool_assertion_message(
    tool: str | None,
    expected_lines: list[str],
    actual: int,
    calls: list[TraceEvent],
) -> str:
    label = tool or "*"
    lines = [
        f"Tool call assertion failed for {label}",
        *expected_lines,
        f"actual count {actual}",
        "observed tool calls:",
    ]
    if calls:
        lines.extend(f"- {_format_tool_call(event)}" for event in calls)
    else:
        lines.append("- <none>")
    return "\n".join(lines)


def _format_tool_call(event: TraceEvent) -> str:
    tool = event.tool or "<unknown>"
    if event.raw:
        return f"{tool} raw={event.raw!r}"
    return tool


__all__ = [
    "assert_tool_called",
    "assert_tool_not_called",
    "tool_calls",
]
