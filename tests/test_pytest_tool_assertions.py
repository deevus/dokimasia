from __future__ import annotations

import pytest

from dokimasia.core.model import TraceEvent
from dokimasia.pytest import assert_tool_called, assert_tool_not_called, tool_calls


def _result_with_events(events: list[TraceEvent]):
    return type("Result", (), {"trace_events": events})()


def test_tool_calls_filters_tool_call_events_and_preserves_raw_evidence():
    raw_call = {"toolName": "get_function", "args": {"function_names": ["finalizeCheckout"]}}
    result = _result_with_events(
        [
            TraceEvent(kind="agent.message", text="I'll inspect the code"),
            TraceEvent(kind="tool.call", tool="get_file_skeleton", raw={"toolName": "get_file_skeleton"}),
            TraceEvent(kind="tool.call", tool="get_function", raw=raw_call),
            TraceEvent(kind="skill.loaded", name="using-superpowers"),
        ]
    )

    matches = tool_calls(result, tool="get_function")

    assert matches == [TraceEvent(kind="tool.call", tool="get_function", raw=raw_call)]
    assert matches[0].raw is raw_call


def test_assert_tool_called_verifies_exact_tool_name_and_count_constraints():
    result = _result_with_events(
        [
            TraceEvent(kind="tool.call", tool="read"),
            TraceEvent(kind="tool.call", tool="read_file"),
            TraceEvent(kind="tool.call", tool="get_file_skeleton"),
            TraceEvent(kind="tool.call", tool="get_file_skeleton"),
        ]
    )

    assert_tool_called(result, tool="read", times=1)
    assert_tool_called(result, tool="read_file", times=1)
    assert_tool_called(result, tool="get_file_skeleton")
    assert_tool_called(result, tool="get_file_skeleton", times=2)
    assert_tool_called(result, tool="get_file_skeleton", min=1)
    assert_tool_called(result, tool="get_file_skeleton", max=2)
    assert_tool_called(result, tool="get_function", max=0)

    with pytest.raises(AssertionError, match="expected count == 1"):
        assert_tool_called(result, tool="get_file_skeleton", times=1)


def test_assert_tool_called_rejects_conflicting_count_constraints():
    result = _result_with_events([])

    with pytest.raises(ValueError, match="times cannot be combined with min or max"):
        assert_tool_called(result, tool="get_file_skeleton", times=1, min=1)


def test_assert_tool_not_called_requires_zero_matching_tool_calls():
    result = _result_with_events(
        [
            TraceEvent(kind="tool.call", tool="read_file"),
            TraceEvent(kind="tool.call", tool="get_file_skeleton"),
        ]
    )

    assert_tool_not_called(result, tool="get_function")

    with pytest.raises(AssertionError, match="expected count == 0"):
        assert_tool_not_called(result, tool="read_file")


def test_assert_tool_called_supports_where_predicates_over_raw_arguments():
    result = _result_with_events(
        [
            TraceEvent(
                kind="tool.call",
                tool="get_function",
                raw={"args": {"function_names": ["finalizeCheckout"]}},
            ),
            TraceEvent(
                kind="tool.call",
                tool="get_function",
                raw={"args": {"function_names": ["calculateTax"]}},
            ),
        ]
    )

    matches = tool_calls(
        result,
        tool="get_function",
        where=lambda event: "finalizeCheckout" in event.raw.get("args", {}).get("function_names", []),
    )
    assert len(matches) == 1
    assert matches[0].raw["args"]["function_names"] == ["finalizeCheckout"]

    assert_tool_called(
        result,
        tool="get_function",
        where=lambda event: "finalizeCheckout" in event.raw.get("args", {}).get("function_names", []),
        times=1,
    )


def test_assert_tool_called_failure_lists_observed_tool_calls_and_raw_evidence():
    result = _result_with_events(
        [
            TraceEvent(kind="tool.call", tool="read_file", raw={"args": {"path": "src/checkout.ts"}}),
            TraceEvent(kind="tool.call", tool="get_file_skeleton", raw={"args": {"paths": ["src/checkout.ts"]}}),
        ]
    )

    with pytest.raises(AssertionError) as raised:
        assert_tool_called(result, tool="get_function")

    message = str(raised.value)
    assert "Tool call assertion failed for get_function" in message
    assert "observed tool calls:" in message
    assert "read_file" in message
    assert "get_file_skeleton" in message
    assert "src/checkout.ts" in message


def test_assert_tool_called_failure_lists_none_when_no_tool_calls_were_observed():
    result = _result_with_events([TraceEvent(kind="agent.message", text="No tools needed")])

    with pytest.raises(AssertionError) as raised:
        assert_tool_called(result, tool="read_file")

    assert "- <none>" in str(raised.value)
