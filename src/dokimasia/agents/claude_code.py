from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Iterable

from dokimasia.agents.base import (
    DOKIMASIA_EXTRA_ARGS_ENV_VAR,
    DOKIMASIA_MODEL_ENV_VAR,
    DOKIMASIA_PROVIDER_ENV_VAR,
    DOKIMASIA_THINKING_ENV_VAR,
    resolve_extra_args,
    resolve_option,
)
from dokimasia.core.model import AgentRunResult, McpCall, TraceEvent
from dokimasia.core.json import decode_nested_json_strings

_SKILL_TEXT = re.compile(r"\bUsing\s+([A-Za-z0-9_-]+)\b")


def _extract_texts(obj: object) -> Iterable[str]:
    if isinstance(obj, dict):
        if obj.get("type") == "text" and isinstance(obj.get("text"), str):
            yield obj["text"]
        for value in obj.values():
            yield from _extract_texts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _extract_texts(item)


def _decode_subprocess_output(output: str | bytes | None) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return ""


def parse_claude_stream_json(lines: list[str]) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    seen_skills: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue

        for text in _extract_texts(raw):
            events.append(TraceEvent(kind="agent.message", text=text, raw=raw))
            match = _SKILL_TEXT.search(text)
            if match and match.group(1) not in seen_skills:
                seen_skills.add(match.group(1))
                events.append(TraceEvent(kind="skill.loaded", name=match.group(1), raw=raw))

        for content in raw.get("message", {}).get("content", []) if isinstance(raw, dict) else []:
            if isinstance(content, dict) and content.get("type") == "tool_use":
                tool_name = str(content.get("name"))
                events.append(TraceEvent(kind="tool.call", tool=tool_name, raw=raw))
                tool_input = content.get("input", {})
                if tool_name.lower() == "skill" and isinstance(tool_input, dict):
                    skill = tool_input.get("skill") or tool_input.get("name")
                    if isinstance(skill, str) and skill not in seen_skills:
                        seen_skills.add(skill)
                        events.append(TraceEvent(kind="skill.loaded", name=skill, raw=raw))
    return events


def parse_claude_mcp_calls(lines: list[str]) -> list[McpCall]:
    tool_uses: list[dict[str, object]] = []
    tool_results_by_id: dict[str, dict[str, object]] = {}

    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue

        for content in _message_content(raw):
            if content.get("type") == "tool_use":
                parsed_name = _parse_claude_mcp_tool_name(content.get("name"))
                if parsed_name is not None:
                    tool_uses.append(content)
            elif content.get("type") == "tool_result":
                tool_use_id = content.get("tool_use_id")
                if isinstance(tool_use_id, str):
                    tool_results_by_id[tool_use_id] = content

    calls: list[McpCall] = []
    for sequence, tool_use in enumerate(tool_uses, start=1):
        parsed_name = _parse_claude_mcp_tool_name(tool_use.get("name"))
        if parsed_name is None:
            continue
        server, tool = parsed_name
        arguments = tool_use.get("input", {})
        if not isinstance(arguments, dict):
            arguments = {}
        tool_use_id = tool_use.get("id")
        tool_result = tool_results_by_id.get(tool_use_id) if isinstance(tool_use_id, str) else None
        calls.append(
            McpCall(
                server=server,
                tool=tool,
                mode="call",
                arguments=decode_nested_json_strings(arguments),
                result=None if tool_result is None else tool_result.get("content"),
                error=_claude_mcp_result_error(tool_result),
                sequence=sequence,
                call_id=tool_use_id if isinstance(tool_use_id, str) else None,
                raw={"tool_use": tool_use, "tool_result": tool_result},
            )
        )
    return calls


def _claude_mcp_result_error(tool_result: dict[str, object] | None) -> str | None:
    if tool_result is None or tool_result.get("is_error") is not True:
        return None
    return _claude_tool_result_text(tool_result.get("content")) or "MCP operation failed"


def _claude_tool_result_text(content: object) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None

    text = "\n".join(_text_blocks(content))
    return text or None


def _text_blocks(content: list[object]) -> Iterable[str]:
    for item in content:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        text = item["text"].strip()
        if text:
            yield text


def _message_content(raw: dict[str, object]) -> Iterable[dict[str, object]]:
    message = raw.get("message")
    if not isinstance(message, dict):
        return
    content_items = message.get("content", [])
    if not isinstance(content_items, list):
        return
    for content in content_items:
        if isinstance(content, dict):
            yield content


def _parse_claude_mcp_tool_name(name: object) -> tuple[str, str] | None:
    if not isinstance(name, str):
        return None
    parts = name.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


class ClaudeCodeAdapter:
    def __init__(
        self,
        claude_bin: str = "claude",
        plugin_dir: Path | None = None,
        *,
        model: str | None = None,
        extra_args: Sequence[str] | None = None,
    ):
        self.claude_bin = claude_bin
        self.plugin_dir = plugin_dir
        self.model = model
        self.extra_args = tuple(extra_args or ())
        self._extra_args = extra_args

    def run(
        self,
        prompt: str,
        workspace: Path,
        artifact_dir: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> AgentRunResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent.stdout.jsonl"
        stderr_path = artifact_dir / "agent.stderr.txt"
        merged_env = os.environ.copy()
        merged_env.update(env)
        if DOKIMASIA_PROVIDER_ENV_VAR in merged_env or DOKIMASIA_THINKING_ENV_VAR in merged_env:
            raise ValueError("DOKIMASIA_PROVIDER and DOKIMASIA_THINKING are only supported for pi agents")

        command = [
            self.claude_bin,
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
        ]
        if self.plugin_dir is not None:
            command.extend(["--plugin-dir", str(self.plugin_dir)])
        model = resolve_option(self.model, merged_env, DOKIMASIA_MODEL_ENV_VAR)
        extra_args = resolve_extra_args(self._extra_args, merged_env, DOKIMASIA_EXTRA_ARGS_ENV_VAR)
        if model is not None:
            command.extend(["--model", model])
        command.extend(extra_args)
        command.append(prompt)

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                env=merged_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
            timed_out = False
            stdout = _decode_subprocess_output(completed.stdout)
            stderr = _decode_subprocess_output(completed.stderr)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _decode_subprocess_output(exc.stdout)
            stderr = _decode_subprocess_output(exc.stderr)
            exit_code = 124

        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        lines = stdout.splitlines()
        return AgentRunResult(
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            raw_trace_path=stdout_path,
            trace_events=parse_claude_stream_json(lines),
            duration_seconds=time.monotonic() - started,
            mcp_calls=parse_claude_mcp_calls(lines),
            timed_out=timed_out,
        )
