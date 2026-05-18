from __future__ import annotations

from pathlib import Path

import pytest

from dokimasia.core.model import AgentRunResult, McpCall
from dokimasia.pytest import DokiResult, assert_mcp_called, assert_mcp_not_called, normalize_mcp_call


class FakeMcpAdapter:
    def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent.stdout.txt"
        stderr_path = artifact_dir / "agent.stderr.txt"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return AgentRunResult(
            exit_code=0,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            raw_trace_path=None,
            trace_events=[],
            duration_seconds=0.01,
            mcp_calls=[
                {
                    "sequence": 7,
                    "server": "doki-ledger",
                    "tool": "record_transaction",
                    "arguments": {"account": "supplies", "amount_cents": 4200},
                    "result": {"id": "txn-000001"},
                    "is_error": False,
                    "raw": {"tool_use_id": "toolu_1"},
                }
            ],
        )


def test_doki_result_exposes_normalized_mcp_calls_from_agent_result(tmp_path: Path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    agent_result = AgentRunResult(
        exit_code=0,
        stdout_path=stdout,
        stderr_path=stderr,
        raw_trace_path=None,
        trace_events=[],
        duration_seconds=0.01,
        mcp_calls=[
            {
                "server": "doki-ledger",
                "tool": "record_transaction",
                "arguments": {"account": "travel"},
                "is_error": False,
                "sequence": 3,
                "raw": {"adapter": "fake"},
            }
        ],
    )

    result = DokiResult.from_agent_result(agent_result, tmp_path / "artifacts")

    assert result.mcp_calls == [
        McpCall(
            server="doki-ledger",
            tool="record_transaction",
            arguments={"account": "travel"},
            sequence=3,
            raw={"adapter": "fake"},
        )
    ]

    assert result.mcp_calls[0].is_error is False


def test_doki_run_preserves_fake_adapter_mcp_evidence(doki_factory, tmp_path: Path):
    result = doki_factory(agent=FakeMcpAdapter(), workspace=tmp_path / "workspace").run("record a transaction")

    assert result.mcp_calls[0].server == "doki-ledger"
    assert result.mcp_calls[0].tool == "record_transaction"
    assert result.mcp_calls[0].arguments["amount_cents"] == 4200

    assert result.mcp_calls[0].result == {"id": "txn-000001"}
    assert result.mcp_calls[0].is_error is False
    assert result.mcp_calls[0].raw == {"tool_use_id": "toolu_1"}


def test_normalized_mcp_call_derives_error_state_from_trimmed_error():
    result = DokiResult.from_agent_result(
        AgentRunResult(
            exit_code=0,
            stdout_path=Path("stdout.txt"),
            stderr_path=Path("stderr.txt"),
            raw_trace_path=None,
            trace_events=[],
            duration_seconds=0.01,
            mcp_calls=[
                {"server": "doki-ledger", "tool": "record_transaction", "error": "  tool failed  "},
                {"server": "doki-ledger", "tool": "get_balance", "error": "   "},
            ],
        ),
        Path("artifacts"),
    )

    failed, succeeded = result.mcp_calls
    assert failed.error == "tool failed"
    assert failed.is_error is True
    assert succeeded.error is None
    assert succeeded.is_error is False


def test_normalize_mcp_call_decodes_nested_json_string_arguments_and_preserves_raw():
    raw = {
        "server": "doki-ledger",
        "tool": "record_transaction",
        "arguments": {
            "account": "travel",
            "payload": '{"amount_cents": 4200, "tags": ["flight"]}',
        },
    }

    call = normalize_mcp_call(raw)

    assert call.arguments == {
        "account": "travel",
        "payload": {"amount_cents": 4200, "tags": ["flight"]},
    }
    assert call.raw is raw


def test_normalize_mcp_call_classifies_generic_is_error_metadata():
    call = normalize_mcp_call({"server": "github", "tool": "create_issue", "is_error": True})

    assert call.error == "MCP operation failed"
    assert call.is_error is True


def test_normalize_mcp_call_classifies_camel_case_is_error_metadata():
    call = normalize_mcp_call({"server": "github", "tool": "create_issue", "isError": True})

    assert call.error == "MCP operation failed"
    assert call.is_error is True


def test_assert_mcp_called_verifies_matching_call():
    result = type(
        "Result",
        (),
        {
            "mcp_calls": [
                McpCall(
                    server="doki-ledger",
                    tool="record_transaction",
                    arguments={"account": "supplies"},
                    sequence=1,
                )
            ]
        },
    )()

    assert_mcp_called(result, server="doki-ledger", tool="record_transaction")


def test_assert_mcp_called_supports_count_constraints():
    result = type(
        "Result",
        (),
        {
            "mcp_calls": [
                McpCall(server="doki-ledger", tool="record_transaction", sequence=1),
                McpCall(server="doki-ledger", tool="record_transaction", sequence=2),
                McpCall(server="github", tool="create_issue", sequence=3),
            ]
        },
    )()

    assert_mcp_called(result, server="doki-ledger", tool="record_transaction", times=2)
    assert_mcp_called(result, server="doki-ledger", tool="record_transaction", min=1)
    assert_mcp_called(result, server="doki-ledger", tool="record_transaction", max=2)
    assert_mcp_called(result, server="slack", tool="post_message", max=0)

    with pytest.raises(AssertionError, match="expected count == 1"):
        assert_mcp_called(result, server="doki-ledger", tool="record_transaction", times=1)


def test_assert_mcp_called_rejects_conflicting_count_constraints():
    result = type("Result", (), {"mcp_calls": []})()

    with pytest.raises(ValueError, match="times cannot be combined with min or max"):
        assert_mcp_called(result, server="doki-ledger", tool="record_transaction", times=1, min=1)


def test_assert_mcp_called_failure_lists_observed_calls():
    result = type(
        "Result",
        (),
        {"mcp_calls": [McpCall(server="doki-ledger", tool="record_transaction", sequence=1)]},
    )()

    with pytest.raises(AssertionError) as raised:
        assert_mcp_called(result, server="github", tool="create_issue")

    message = str(raised.value)
    assert "MCP call assertion failed for github.create_issue" in message
    assert "observed MCP calls:" in message
    assert "doki-ledger.record_transaction" in message


def test_assert_mcp_called_filters_by_mode_success_and_predicate():
    result = type(
        "Result",
        (),
        {
            "mcp_calls": [
                McpCall(server="doki-ledger", tool="record_transaction", arguments={"account": "travel"}, mode="call"),
                McpCall(server="doki-ledger", tool="record_transaction", mode="call", error="write failed"),
                McpCall(server="doki-ledger", tool="search", mode="search"),
            ]
        },
    )()

    assert_mcp_called(
        result,
        server="doki-ledger",
        tool="record_transaction",
        success=True,
        where=lambda call: call.arguments.get("account") == "travel",
        times=1,
    )
    assert_mcp_called(result, server="doki-ledger", tool="record_transaction", success=False, times=1)
    assert_mcp_called(result, mode="search", times=1)


def test_assert_mcp_called_defaults_to_call_mode_so_discovery_does_not_satisfy_tool_call_assertions():
    result = type("Result", (), {"mcp_calls": [McpCall(server="doki-ledger", tool="search", mode="search")]})()

    assert_mcp_not_called(result, server="doki-ledger", tool="search")

    with pytest.raises(AssertionError) as raised:
        assert_mcp_called(result, server="doki-ledger", tool="search")

    assert "mode=search" in str(raised.value)


def test_assert_mcp_called_failure_message_includes_arguments_modes_and_errors():
    result = type(
        "Result",
        (),
        {
            "mcp_calls": [
                McpCall(
                    server="doki-ledger",
                    tool="record_transaction",
                    arguments={"account": "travel"},
                    mode="call",
                    error="write failed",
                    sequence=1,
                )
            ]
        },
    )()

    with pytest.raises(AssertionError) as raised:
        assert_mcp_called(result, server="github", tool="create_issue")

    message = str(raised.value)
    assert "#1 doki-ledger.record_transaction mode=call (error)" in message
    assert "arguments={'account': 'travel'}" in message
    assert "error='write failed'" in message
