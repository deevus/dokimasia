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
