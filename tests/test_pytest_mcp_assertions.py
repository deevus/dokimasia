from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dokimasia.core.model import AgentRunResult, McpCall
from dokimasia.pytest import DokiResult, assert_mcp_call, mcp


def result_with_mcp_calls(*calls):
    return SimpleNamespace(mcp_calls=list(calls))


def test_mcp_matcher_filters_server_tool_arguments_and_success_state():
    result = result_with_mcp_calls(
        McpCall(
            server="github",
            tool="create_issue",
            arguments={"repo": "dokimasia", "title": "Fix evidence"},
            result={"number": 33},
            order=1,
            raw={"kind": "mcp.call"},
        ),
        McpCall(
            server="github",
            tool="add_label",
            arguments={"label": "ready-for-agent"},
            error={"message": "permission denied"},
            order=2,
            raw={"kind": "mcp.error"},
        ),
    )

    assert_mcp_call(result, mcp.match(server="github", tool="create_issue", arguments={"repo": "dokimasia"}))
    assert_mcp_call(result, mcp.match(server="github", ok=True), times=1)
    assert_mcp_call(result, mcp.match(server="github", ok=False), times=1)

    with pytest.raises(AssertionError, match="expected count >= 1"):
        assert_mcp_call(result, mcp.match(server="github", tool="delete_issue"))


def test_mcp_assertion_supports_count_constraints():
    result = result_with_mcp_calls(
        {"server": "github", "tool": "create_issue", "arguments": {"repo": "dokimasia"}, "order": 1},
        {"server": "github", "tool": "create_issue", "arguments": {"repo": "other"}, "order": 2},
    )

    assert_mcp_call(result, mcp.match(server="github", tool="create_issue"), times=2)
    assert_mcp_call(result, mcp.match(server="github", tool="create_issue"), min=1)
    assert_mcp_call(result, mcp.match(server="github", tool="create_issue"), max=2)

    with pytest.raises(ValueError, match="times cannot be combined"):
        assert_mcp_call(result, mcp.match(server="github"), times=1, min=1)

    with pytest.raises(AssertionError, match="expected count == 1"):
        assert_mcp_call(result, mcp.match(server="github", tool="create_issue"), times=1)


def test_mcp_failure_message_lists_observed_calls():
    result = result_with_mcp_calls(
        McpCall(server="filesystem", tool="write_file", arguments={"path": "README.md"}, order=3)
    )

    with pytest.raises(AssertionError) as raised:
        assert_mcp_call(result, mcp.match(server="github", tool="create_issue"))

    message = str(raised.value)
    assert "MCP call assertion failed for github.create_issue" in message
    assert "actual count 0" in message
    assert "observed MCP calls:" in message
    assert "filesystem.write_file" in message


def test_doki_result_exposes_normalized_adapter_mcp_calls_without_changing_command_evidence(tmp_path: Path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    raw_mcp_call = {
        "server": "github",
        "tool": "create_issue",
        "args": {"repo": "dokimasia"},
        "result": {"number": 33},
        "order": "4",
    }
    agent_result = AgentRunResult(
        exit_code=0,
        stdout_path=stdout,
        stderr_path=stderr,
        raw_trace_path=None,
        trace_events=[],
        duration_seconds=0.01,
        commands=[{"executable": "tea", "argv": ["issues", "create"], "exit_code": 0}],
        mcp_calls=[raw_mcp_call],
    )

    result = DokiResult.from_agent_result(agent_result, tmp_path / "artifacts")

    assert result.commands[0].executable == "tea"
    assert result.commands[0].argv == ["issues", "create"]
    assert result.mcp_calls == [
        McpCall(
            server="github",
            tool="create_issue",
            arguments={"repo": "dokimasia"},
            result={"number": 33},
            order=4,
            raw=raw_mcp_call,
        )
    ]
