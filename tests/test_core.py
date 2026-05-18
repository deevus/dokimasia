from __future__ import annotations

import json
from pathlib import Path


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
