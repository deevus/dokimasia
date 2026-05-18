from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dokimasia.core.model import McpCall

WherePredicate = Callable[[McpCall], bool]

_MISSING = object()


@dataclass(frozen=True)
class McpCallMatcher:
    server: str | None = None
    tool: str | None = None
    arguments: Mapping[str, Any] | None = None
    ok: bool | None = None
    where: WherePredicate | None = None
    label: str = "mcp-call"

    def matches(self, call: Any) -> bool:
        mcp_call = normalize_call(call)
        if self.server is not None and mcp_call.server != self.server:
            return False
        if self.tool is not None and mcp_call.tool != self.tool:
            return False
        if self.arguments is not None and not _arguments_match(mcp_call.arguments, self.arguments):
            return False
        if self.ok is not None and mcp_call.ok is not self.ok:
            return False
        if self.where is not None and not self.where(mcp_call):
            return False
        return True

    def __call__(self, call: Any) -> bool:
        return self.matches(call)

    def filter(self, calls: Sequence[Any]) -> list[McpCall]:
        return [normalize_call(call) for call in calls if self.matches(call)]


def match(
    *,
    server: str | None = None,
    tool: str | None = None,
    arguments: Mapping[str, Any] | None = None,
    ok: bool | None = None,
    where: WherePredicate | None = None,
    label: str | None = None,
) -> McpCallMatcher:
    """Create a matcher for normalized MCP calls recorded by an adapter."""

    if arguments is not None and not isinstance(arguments, Mapping):
        raise ValueError("arguments must be a mapping")
    return McpCallMatcher(
        server=server,
        tool=tool,
        arguments=arguments,
        ok=ok,
        where=where,
        label=label or _generate_label(server, tool),
    )


def assert_mcp_call(
    result: Any,
    matcher: McpCallMatcher,
    *,
    times: int | None = None,
    min: int | None = None,
    max: int | None = None,
) -> None:
    """Assert that result.mcp_calls includes calls matching an MCP matcher."""

    if times is not None and (min is not None or max is not None):
        raise ValueError("times cannot be combined with min or max")

    calls = [normalize_call(call) for call in getattr(result, "mcp_calls", [])]
    matching_calls = [call for call in calls if matcher.matches(call)]
    actual = len(matching_calls)

    expected_lines = _expected_count_lines(times=times, min=min, max=max)
    if not expected_lines:
        expected_lines = ["expected count >= 1"]
        if actual >= 1:
            return
    elif _count_satisfies(actual, times=times, min=min, max=max):
        return

    raise AssertionError(_mcp_assertion_message(matcher, expected_lines, actual, calls))


def normalize_call(call: Any) -> McpCall:
    if isinstance(call, McpCall):
        return call

    server = _field(call, "server")
    tool = _field(call, "tool")
    if server in (_MISSING, None, ""):
        raise ValueError("MCP call must include server")
    if tool in (_MISSING, None, ""):
        raise ValueError("MCP call must include tool")

    arguments = _field(call, "arguments")
    if arguments is _MISSING:
        arguments = _field(call, "args")
    if arguments in (_MISSING, None):
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise ValueError("MCP call arguments must be a mapping")

    result = _field(call, "result")
    error = _field(call, "error")
    order = _field(call, "order")
    raw = _field(call, "raw")

    return McpCall(
        server=str(server),
        tool=str(tool),
        arguments=dict(arguments),
        result=None if result is _MISSING else result,
        error=None if error is _MISSING else error,
        order=None if order in (_MISSING, None) else int(order),
        raw=call if raw is _MISSING else raw,
    )


def _arguments_match(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(actual.get(key, _MISSING) == value for key, value in expected.items())


def _expected_count_lines(
    *,
    times: int | None,
    min: int | None,
    max: int | None,
) -> list[str]:
    if times is not None:
        return [f"expected count == {times}"]

    lines: list[str] = []
    if min is not None:
        lines.append(f"expected count >= {min}")
    if max is not None:
        lines.append(f"expected count <= {max}")
    return lines


def _count_satisfies(
    actual: int,
    *,
    times: int | None,
    min: int | None,
    max: int | None,
) -> bool:
    if times is not None:
        return actual == times
    if min is not None and actual < min:
        return False
    if max is not None and actual > max:
        return False
    return True


def _mcp_assertion_message(
    matcher: McpCallMatcher,
    expected_lines: list[str],
    actual: int,
    calls: Sequence[McpCall],
) -> str:
    lines = [
        f"MCP call assertion failed for {matcher.label}",
        *expected_lines,
        f"actual count {actual}",
        "observed MCP calls:",
    ]
    if calls:
        lines.extend(f"- {_format_call(call)}" for call in calls)
    else:
        lines.append("- <none>")
    return "\n".join(lines)


def _format_call(call: McpCall) -> str:
    state = "ok" if call.ok else "error"
    return f"{call.server}.{call.tool} order={call.order} state={state} arguments={call.arguments!r}"


def _field(call: Any, name: str) -> Any:
    if isinstance(call, Mapping):
        return call.get(name, _MISSING)
    return getattr(call, name, _MISSING)


def _generate_label(server: str | None, tool: str | None) -> str:
    parts = [part for part in [server, tool] if part]
    if not parts:
        return "mcp-call"
    return ".".join(parts)


__all__ = [
    "McpCallMatcher",
    "assert_mcp_call",
    "match",
    "normalize_call",
]
