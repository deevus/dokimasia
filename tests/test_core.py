from __future__ import annotations

import json
from pathlib import Path


PI_MCP_ADAPTER_EVENTS = Path(__file__).parent / "fixtures" / "pi_mcp_adapter_events.json"


def _pi_mcp_adapter_events(name: str) -> list[dict]:
    return json.loads(PI_MCP_ADAPTER_EVENTS.read_text(encoding="utf-8"))[name]


def _pi_mcp_adapter_jsonl(name: str) -> list[str]:
    return [json.dumps(event) for event in _pi_mcp_adapter_events(name)]


def test_claude_parser_extracts_plugin_qualified_skill_loaded():
    from dokimasia.agents.claude_code import parse_claude_stream_json

    events = parse_claude_stream_json(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Skill",
                                "input": {"skill": "plugin:create-record"},
                            }
                        ]
                    },
                }
            ),
        ]
    )

    assert "plugin:create-record" in [event.name for event in events if event.kind == "skill.loaded"]


def test_claude_mcp_parser_pairs_successful_tool_result():
    from dokimasia.agents.claude_code import parse_claude_mcp_calls
    from dokimasia.core.model import McpCall

    calls = parse_claude_mcp_calls(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "mcp__doki-ledger__record_transaction",
                                "input": {"account": "travel", "amount_cents": 4200},
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "content": [{"type": "text", "text": "recorded txn-1"}],
                            }
                        ]
                    },
                }
            ),
        ]
    )

    assert calls == [
        McpCall(
            server="doki-ledger",
            tool="record_transaction",
            arguments={"account": "travel", "amount_cents": 4200},
            result=[{"type": "text", "text": "recorded txn-1"}],
            sequence=1,
            call_id="toolu_1",
            raw={
                "tool_use": {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "mcp__doki-ledger__record_transaction",
                    "input": {"account": "travel", "amount_cents": 4200},
                },
                "tool_result": {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": [{"type": "text", "text": "recorded txn-1"}],
                },
            },
        )
    ]


def test_claude_mcp_parser_preserves_call_without_result():
    from dokimasia.agents.claude_code import parse_claude_mcp_calls

    calls = parse_claude_mcp_calls(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_missing",
                                "name": "mcp__github__create_issue",
                                "input": {"title": "Bug"},
                            }
                        ]
                    },
                }
            )
        ]
    )

    assert len(calls) == 1
    assert calls[0].server == "github"
    assert calls[0].tool == "create_issue"
    assert calls[0].arguments == {"title": "Bug"}
    assert calls[0].result is None
    assert calls[0].raw["tool_result"] is None


def test_claude_mcp_parser_classifies_error_tool_result_and_decodes_nested_arguments():
    from dokimasia.agents.claude_code import parse_claude_mcp_calls

    calls = parse_claude_mcp_calls(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "mcp__github__create_issue",
                                "input": {"payload": '{"title": "Bug"}'},
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "is_error": True,
                                "content": [{"type": "text", "text": "permission denied"}],
                            }
                        ]
                    },
                }
            ),
        ]
    )

    assert len(calls) == 1
    assert calls[0].arguments == {"payload": {"title": "Bug"}}
    assert calls[0].error == "permission denied"
    assert calls[0].is_error is True


def test_claude_mcp_parser_ignores_non_mcp_tool_uses():
    from dokimasia.agents.claude_code import parse_claude_mcp_calls

    calls = parse_claude_mcp_calls(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_read",
                                "name": "Read",
                                "input": {"file_path": "README.md"},
                            },
                            {"type": "tool_use", "id": "toolu_malformed", "name": "mcp__missing_tool", "input": {}},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {"type": "tool_result", "tool_use_id": "toolu_read", "content": "read result"},
                        ]
                    },
                }
            ),
        ]
    )

    assert calls == []


def test_claude_code_adapter_returns_mcp_calls_from_stream_json(tmp_path):
    from dokimasia.agents.claude_code import ClaudeCodeAdapter

    claude_bin = tmp_path / "claude"
    claude_bin.write_text(
        f"#!{__import__('sys').executable}\n"
        "import json\n"
        "events = [\n"
        "    {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'toolu_1', 'name': 'mcp__doki-ledger__record_transaction', 'input': {'account': 'travel'}}]}},\n"
        "    {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': [{'type': 'text', 'text': 'ok'}]}]}},\n"
        "]\n"
        "for event in events:\n"
        "    print(json.dumps(event))\n",
        encoding="utf-8",
    )
    claude_bin.chmod(0o755)

    result = ClaudeCodeAdapter(claude_bin=str(claude_bin)).run(
        "record it",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={},
        timeout_seconds=5,
    )

    assert result.mcp_calls[0].server == "doki-ledger"
    assert result.mcp_calls[0].tool == "record_transaction"
    assert result.mcp_calls[0].arguments == {"account": "travel"}
    assert result.mcp_calls[0].result == [{"type": "text", "text": "ok"}]


def test_pi_parser_extracts_skill_loaded_from_current_skill_read():
    from dokimasia.agents.pi import parse_pi_json_events

    events = parse_pi_json_events(
        [
            json.dumps(
                {
                    "type": "tool_execution_start",
                    "toolName": "read",
                    "args": {"path": "/repo/skills/create-record/SKILL.md"},
                }
            ),
        ],
        skills_dir=Path("/repo/skills"),
    )

    assert [event.name for event in events if event.kind == "skill.loaded"] == ["create-record"]


def test_pi_mcp_adapter_parser_normalizes_proxy_call_with_decoded_args():
    from dokimasia.agents.pi import parse_pi_mcp_calls
    from dokimasia.core.model import McpCall

    events = _pi_mcp_adapter_events("proxy_call_with_decoded_args")
    calls = parse_pi_mcp_calls([json.dumps(event) for event in events])

    assert calls == [
        McpCall(
            server="doki-ledger",
            tool="record_transaction",
            arguments={"account": "travel", "amount_cents": 4200},
            result={"id": "txn-000001"},
            sequence=1,
            call_id="call-1",
            raw={"tool_call": events[0], "tool_result": events[1]},
        )
    ]


def test_pi_mcp_adapter_parser_deduplicates_repeated_result_evidence():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    events = _pi_mcp_adapter_events("proxy_call_with_decoded_args")
    lines = [json.dumps(event) for event in [*events, events[1], events[1]]]

    calls = parse_pi_mcp_calls(lines)

    assert len(calls) == 1
    assert calls[0].call_id == "call-1"


def test_pi_mcp_adapter_parser_normalizes_nested_session_message_proxy_call():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("nested_session_message_proxy_call"))

    assert len(calls) == 1
    assert calls[0].server == "doki-ledger"
    assert calls[0].tool == "record_transaction"
    assert calls[0].arguments == {"account": "travel"}
    assert calls[0].result == {"id": "txn-000001"}


def test_pi_mcp_adapter_parser_normalizes_deeply_nested_session_message_proxy_call():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("deeply_nested_session_message_proxy_call"))

    assert len(calls) == 1
    assert calls[0].server == "doki-ledger"
    assert calls[0].tool == "record_transaction"
    assert calls[0].arguments == {"account": "travel"}
    assert calls[0].result == {"id": "txn-000001"}


def test_pi_mcp_adapter_parser_preserves_malformed_proxy_args_without_failing():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("malformed_proxy_args"))

    assert len(calls) == 1
    assert calls[0].arguments == {"args": "not json"}


def test_pi_mcp_adapter_parser_uses_direct_tool_metadata_not_tool_name_prefix():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("direct_tool_success"))

    assert len(calls) == 1
    assert calls[0].server == "doki-ledger"
    assert calls[0].tool == "record_transaction"
    assert calls[0].arguments == {"account": "travel"}
    assert calls[0].result == {"content": [{"type": "text", "text": "recorded txn-000001"}]}


def test_pi_mcp_adapter_parser_records_direct_tool_failure_when_error_metadata_identifies_server():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("direct_tool_failure_without_tool_metadata"))

    assert len(calls) == 1
    assert calls[0].server == "doki-ledger"
    assert calls[0].tool == "record_transaction"
    assert calls[0].error == "ledger write failed"


def test_pi_mcp_adapter_parser_preserves_direct_tool_outer_result_payload():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("direct_tool_success"))

    assert len(calls) == 1
    assert calls[0].result == {"content": [{"type": "text", "text": "recorded txn-000001"}]}


def test_pi_mcp_adapter_parser_treats_details_error_as_failure_evidence():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("proxy_error"))

    assert len(calls) == 1
    assert calls[0].error == "MCP server rejected the request"
    assert calls[0].is_error is True


def test_pi_mcp_adapter_parser_treats_top_level_is_error_as_failure_evidence():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("proxy_top_level_is_error"))

    assert len(calls) == 1
    assert calls[0].error == "MCP operation failed"
    assert calls[0].is_error is True


def test_pi_mcp_adapter_parser_preserves_error_result_without_details():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("proxy_top_level_is_error_without_details"))

    assert len(calls) == 1
    assert calls[0].server == "github"
    assert calls[0].tool == "create_issue"
    assert calls[0].error == "MCP operation failed"
    assert calls[0].result == "permission denied"
    assert calls[0].raw["tool_result"] is not None


def test_pi_mcp_adapter_parser_decodes_nested_proxy_json_arguments():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("proxy_nested_json_args"))

    assert len(calls) == 1
    assert calls[0].arguments == {"payload": {"amount_cents": 4200}}


def test_pi_mcp_adapter_parser_preserves_unpaired_discovery_proxy_call():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("unpaired_discovery_proxy_call"))

    assert len(calls) == 1
    assert calls[0].mode == "discovery"
    assert calls[0].tool == "discovery"
    assert calls[0].result is None


def test_pi_mcp_adapter_parser_represents_discovery_modes_separately_from_calls():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("discovery_and_non_mcp_tools"))

    assert len(calls) == 1
    assert calls[0].server == "docfork"
    assert calls[0].tool == "search"
    assert calls[0].mode == "search"


def test_pi_mcp_adapter_parser_preserves_unpaired_proxy_call_evidence():
    from dokimasia.agents.pi import parse_pi_mcp_calls

    calls = parse_pi_mcp_calls(_pi_mcp_adapter_jsonl("unpaired_proxy_call"))

    assert len(calls) == 1
    assert calls[0].server == "doki-ledger"
    assert calls[0].tool == "record_transaction"
    assert calls[0].arguments == {"account": "travel"}
    assert calls[0].result is None
    assert calls[0].raw["tool_result"] is None


def test_pi_adapter_accepts_custom_mcp_normalizer(tmp_path):
    from dokimasia.agents.pi import PiAdapter
    from dokimasia.core.model import McpCall

    pi_bin = tmp_path / "pi"
    pi_bin.write_text(
        f"#!{__import__('sys').executable}\n"
        "import json\n"
        "print(json.dumps({'type': 'custom_mcp_evidence', 'server': 'custom', 'tool': 'ping'}))\n",
        encoding="utf-8",
    )
    pi_bin.chmod(0o755)

    def custom_normalizer(events):
        return [
            McpCall(server=event["server"], tool=event["tool"], sequence=index)
            for index, event in enumerate(events, start=1)
            if event.get("type") == "custom_mcp_evidence"
        ]

    result = PiAdapter(pi_bin=str(pi_bin), skills_dir=tmp_path, mcp_normalizers=[custom_normalizer]).run(
        "ping",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={},
        timeout_seconds=5,
    )

    assert result.mcp_calls == [McpCall(server="custom", tool="ping", sequence=1)]


def test_pi_adapter_returns_default_pi_mcp_adapter_calls(tmp_path):
    from dokimasia.agents.pi import PiAdapter

    pi_bin = tmp_path / "pi"
    events = repr(_pi_mcp_adapter_events("proxy_call_with_decoded_args"))
    pi_bin.write_text(
        f"#!{__import__('sys').executable}\n"
        "import json\n"
        f"events = {events}\n"
        "for event in events:\n"
        "    print(json.dumps(event))\n",
        encoding="utf-8",
    )
    pi_bin.chmod(0o755)

    result = PiAdapter(pi_bin=str(pi_bin), skills_dir=tmp_path).run(
        "record it",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={},
        timeout_seconds=5,
    )

    assert len(result.mcp_calls) == 1
    assert result.mcp_calls[0].server == "doki-ledger"
    assert result.mcp_calls[0].tool == "record_transaction"
    assert result.mcp_calls[0].arguments == {"account": "travel", "amount_cents": 4200}
