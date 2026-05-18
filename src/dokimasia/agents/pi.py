from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import jmespath

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


def _decode_subprocess_output(output: str | bytes | None) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return ""


PiMcpNormalizer = Callable[[list[dict[str, Any]]], list[McpCall]]
_PI_MCP_METADATA_KEYS = frozenset(("mode", "server", "tool", "mcpResult", "error"))
_PI_MCP_RESULT_DETAILS_CANDIDATES = jmespath.compile("[details, result.details, result]")


def _content_texts(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return texts
    return []


def _skill_from_read_path(path: str, skills_dir: Path) -> str | None:
    try:
        relative = Path(path).resolve().relative_to(skills_dir.resolve())
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) == 2 and parts[1] == "SKILL.md":
        return parts[0]
    return None


def parse_pi_json_events(lines: list[str], skills_dir: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    seen_skills: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = raw.get("type") if isinstance(raw, dict) else None
        if event_type == "tool_execution_start":
            tool_name = str(raw.get("toolName") or "")
            events.append(TraceEvent(kind="tool.call", tool=tool_name, raw=raw))
            args = raw.get("args", {})
            path = args.get("path") if isinstance(args, dict) else None
            if tool_name == "read" and isinstance(path, str):
                skill = _skill_from_read_path(path, skills_dir)
                if skill and skill not in seen_skills:
                    seen_skills.add(skill)
                    events.append(TraceEvent(kind="skill.loaded", name=skill, raw=raw))

        if event_type in {"message_start", "message_update", "message_end"}:
            message = raw.get("message", {})
            if isinstance(message, dict):
                for text in _content_texts(message.get("content")):
                    events.append(TraceEvent(kind="agent.message", text=text, raw=raw))
            assistant_event = raw.get("assistantMessageEvent")
            if isinstance(assistant_event, dict) and isinstance(assistant_event.get("delta"), str):
                events.append(TraceEvent(kind="agent.message", text=assistant_event["delta"], raw=raw))
    return events


def parse_pi_mcp_calls(
    lines: list[str],
    normalizers: Sequence[PiMcpNormalizer] | None = None,
) -> list[McpCall]:
    events = _load_json_events(lines)
    selected_normalizers = DEFAULT_PI_MCP_NORMALIZERS if normalizers is None else tuple(normalizers)
    calls: list[McpCall] = []
    for normalizer in selected_normalizers:
        calls.extend(normalizer(events))
    return calls


def normalize_pi_mcp_adapter_calls(events: list[dict[str, Any]]) -> list[McpCall]:
    """Normalize MCP operation evidence emitted by nicobailon/pi-mcp-adapter."""

    tool_calls_by_id: dict[str, dict[str, Any]] = {}
    paired_tool_call_ids: set[str] = set()
    calls: list[McpCall] = []
    for event in events:
        tool_call_id = _tool_call_id(event)
        if _is_tool_call_event(event) and tool_call_id is not None:
            tool_calls_by_id[tool_call_id] = event
            continue
        if not _is_tool_result_event(event):
            continue

        tool_call = tool_calls_by_id.get(tool_call_id) if tool_call_id is not None else None
        mcp_call = _normalize_pi_mcp_adapter_result(event, tool_call, sequence=len(calls) + 1)
        if mcp_call is not None:
            calls.append(mcp_call)
            if tool_call_id is not None:
                paired_tool_call_ids.add(tool_call_id)

    for tool_call_id, tool_call in tool_calls_by_id.items():
        if tool_call_id in paired_tool_call_ids:
            continue
        mcp_call = _normalize_unpaired_pi_mcp_adapter_tool_call(tool_call, sequence=len(calls) + 1)
        if mcp_call is not None:
            calls.append(mcp_call)
    return calls


DEFAULT_PI_MCP_NORMALIZERS: tuple[PiMcpNormalizer, ...] = (normalize_pi_mcp_adapter_calls,)


def _load_json_events(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            events.extend(_pi_mcp_candidate_events(raw))
    return events


def _pi_mcp_candidate_events(raw: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    _collect_pi_mcp_candidate_events(raw, events)
    return events


def _collect_pi_mcp_candidate_events(raw: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Collect Pi MCP evidence from flat events and known message envelopes.

    Pi MCP evidence can be emitted as flat `tool_execution_*` JSON events, or
    wrapped inside session-log/message envelopes. Some envelopes contain the
    actual tool call at `message.content[]`; others add another layer such as
    `message.message.content[]`.

    Walk only the known Pi container fields recursively so the normalizer can
    find `toolCall`/`toolResult` records without hard-coding one extension
    envelope shape.
    """
    events.append(raw)

    message = raw.get("message")
    if isinstance(message, dict):
        _collect_pi_mcp_candidate_events(message, events)

    content = raw.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                _collect_pi_mcp_candidate_events(item, events)

    tool_results = raw.get("toolResults")
    if isinstance(tool_results, list):
        for item in tool_results:
            if isinstance(item, dict):
                _collect_pi_mcp_candidate_events(item, events)


def _normalize_pi_mcp_adapter_result(
    tool_result: dict[str, Any],
    tool_call: dict[str, Any] | None,
    *,
    sequence: int,
) -> McpCall | None:
    details = _pi_mcp_result_details(tool_result)
    if details is None:
        return _normalize_pi_mcp_adapter_result_without_details(tool_result, tool_call, sequence=sequence)

    mode = _non_empty_string(details.get("mode"))
    if mode is None:
        mode = _proxy_mode(tool_call)
    if mode is None:
        mode = "call"

    server = _non_empty_string(details.get("server"))
    if server is None:
        server = _proxy_field(tool_call, "server")

    tool = _non_empty_string(details.get("tool"))
    if tool is None:
        tool = _proxy_field(tool_call, "tool")
    if tool is None:
        tool = _proxy_operation(tool_call, mode)
    if tool is None and server is not None and _tool_name(tool_call) != "mcp":
        tool = _tool_name(tool_call)

    if mode == "call" and (server is None or tool is None):
        return None
    if mode != "call" and tool is None:
        return None

    return McpCall(
        server=server,
        tool=tool,
        mode=mode,
        arguments=_pi_mcp_arguments(tool_call),
        result=_pi_mcp_result_payload(tool_result, details),
        error=_normalized_error(details.get("error")) or _pi_tool_result_error(tool_result),
        sequence=sequence,
        call_id=_tool_call_id(tool_result) or _tool_call_id(tool_call or {}),
        raw={"tool_call": tool_call, "tool_result": tool_result},
    )


def _normalize_pi_mcp_adapter_result_without_details(
    tool_result: dict[str, Any],
    tool_call: dict[str, Any] | None,
    *,
    sequence: int,
) -> McpCall | None:
    mode = _proxy_mode(tool_call)
    if mode is None:
        mode = "call"

    server = _proxy_field(tool_call, "server")
    tool = _proxy_field(tool_call, "tool")
    if tool is None:
        tool = _proxy_operation(tool_call, mode)

    if mode == "call" and (server is None or tool is None):
        return None
    if mode != "call" and tool is None:
        return None

    return McpCall(
        server=server,
        tool=tool,
        mode=mode,
        arguments=_pi_mcp_arguments(tool_call),
        result=_pi_mcp_result_payload_without_details(tool_result),
        error=_pi_tool_result_error(tool_result),
        sequence=sequence,
        call_id=_tool_call_id(tool_result) or _tool_call_id(tool_call or {}),
        raw={"tool_call": tool_call, "tool_result": tool_result},
    )


def _normalize_unpaired_pi_mcp_adapter_tool_call(tool_call: dict[str, Any], *, sequence: int) -> McpCall | None:
    if _tool_name(tool_call) != "mcp":
        return None

    mode = _proxy_mode(tool_call)
    if mode is None:
        mode = "call"

    server = _proxy_field(tool_call, "server")
    tool = _proxy_field(tool_call, "tool")
    if tool is None:
        tool = _proxy_operation(tool_call, mode)

    if mode == "call" and (server is None or tool is None):
        return None
    if mode != "call" and tool is None:
        return None

    return McpCall(
        server=server,
        tool=tool,
        mode=mode,
        arguments=_pi_mcp_arguments(tool_call),
        result=None,
        sequence=sequence,
        call_id=_tool_call_id(tool_call),
        raw={"tool_call": tool_call, "tool_result": None},
    )


def _is_tool_call_event(event: dict[str, Any]) -> bool:
    return event.get("type") in {"tool_execution_start", "toolCall"}


def _is_tool_result_event(event: dict[str, Any]) -> bool:
    return event.get("type") == "tool_execution_end" or event.get("role") == "toolResult"


def _tool_call_id(event: dict[str, Any]) -> str | None:
    for key in ("toolCallId", "tool_call_id", "id"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _tool_name(event: dict[str, Any] | None) -> str | None:
    if event is None:
        return None
    for key in ("toolName", "name"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _tool_arguments(event: dict[str, Any] | None) -> Any:
    if event is None:
        return {}
    if "args" in event:
        return event["args"]
    return event.get("arguments", {})


def _pi_mcp_result_details(tool_result: dict[str, Any]) -> dict[str, Any] | None:
    for index, candidate in enumerate(_PI_MCP_RESULT_DETAILS_CANDIDATES.search(tool_result)):
        if isinstance(candidate, dict) and (index < 2 or _PI_MCP_METADATA_KEYS.intersection(candidate)):
            return candidate
    return None


def _pi_mcp_result_payload(tool_result: dict[str, Any], details: dict[str, Any]) -> Any:
    if "mcpResult" in details:
        return details["mcpResult"]

    result = tool_result.get("result")
    if isinstance(result, dict) and result.get("details") is details:
        payload = {key: value for key, value in result.items() if key != "details"}
        return payload or None
    if "result" in tool_result:
        return result
    if "content" in tool_result:
        return tool_result["content"]
    return None


def _pi_mcp_result_payload_without_details(tool_result: dict[str, Any]) -> Any:
    if "result" in tool_result:
        return tool_result["result"]
    if "content" in tool_result:
        return tool_result["content"]
    return None


def _proxy_field(tool_call: dict[str, Any] | None, field: str) -> str | None:
    if _tool_name(tool_call) != "mcp":
        return None
    arguments = _tool_arguments(tool_call)
    if not isinstance(arguments, dict):
        return None
    return _non_empty_string(arguments.get(field))


def _proxy_mode(tool_call: dict[str, Any] | None) -> str | None:
    if _tool_name(tool_call) != "mcp":
        return None
    arguments = _tool_arguments(tool_call)
    if not isinstance(arguments, dict):
        return None
    if _non_empty_string(arguments.get("tool")) is not None:
        return "call"
    return _proxy_operation(tool_call, None)


def _proxy_operation(tool_call: dict[str, Any] | None, mode: str | None) -> str | None:
    if _tool_name(tool_call) != "mcp":
        return None
    arguments = _tool_arguments(tool_call)
    if not isinstance(arguments, dict):
        return None
    for candidate in (mode, "connect", "describe", "search", "list", "status", "discovery"):
        if candidate and candidate in arguments:
            return candidate
    return None


def _pi_mcp_arguments(tool_call: dict[str, Any] | None) -> dict[str, Any]:
    if tool_call is None:
        return {}

    arguments = _tool_arguments(tool_call)
    if _tool_name(tool_call) == "mcp":
        return _decode_proxy_mcp_args(arguments)
    return dict(arguments) if isinstance(arguments, dict) else {}


def _decode_proxy_mcp_args(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    mcp_args = arguments.get("args")
    if isinstance(mcp_args, dict):
        return dict(mcp_args)
    if isinstance(mcp_args, str):
        try:
            decoded = json.loads(mcp_args)
        except json.JSONDecodeError:
            return {"args": mcp_args}
        decoded = decode_nested_json_strings(decoded)
        return dict(decoded) if isinstance(decoded, dict) else {"args": decoded}
    if mcp_args is not None:
        return {"args": mcp_args}
    return {}


def _pi_tool_result_error(tool_result: dict[str, Any]) -> str | None:
    if tool_result.get("isError") is True or tool_result.get("is_error") is True:
        return "MCP operation failed"
    return None


def _non_empty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _normalized_error(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


class PiAdapter:
    def __init__(
        self,
        pi_bin: str = "pi",
        skills_dir: Path | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        extra_args: Sequence[str] | None = None,
        mcp_normalizers: Sequence[PiMcpNormalizer] | None = None,
    ):
        self.pi_bin = pi_bin
        self.skills_dir = skills_dir
        self.provider = provider
        self.model = model
        self.thinking = thinking
        self.extra_args = tuple(extra_args or ())
        self._extra_args = extra_args
        self.mcp_normalizers = DEFAULT_PI_MCP_NORMALIZERS if mcp_normalizers is None else tuple(mcp_normalizers)

    def run(
        self,
        prompt: str,
        workspace: Path,
        artifact_dir: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> AgentRunResult:
        if self.skills_dir is None:
            raise ValueError("PiAdapter requires skills_dir so tests use the current checkout's skills")

        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent.stdout.jsonl"
        stderr_path = artifact_dir / "agent.stderr.txt"
        merged_env = os.environ.copy()
        merged_env.update(env)
        command = [
            self.pi_bin,
            "--print",
            "--mode",
            "json",
            "--no-session",
            "--no-skills",
            "--skill",
            str(self.skills_dir),
        ]
        provider = resolve_option(self.provider, merged_env, DOKIMASIA_PROVIDER_ENV_VAR)
        model = resolve_option(self.model, merged_env, DOKIMASIA_MODEL_ENV_VAR)
        thinking = resolve_option(self.thinking, merged_env, DOKIMASIA_THINKING_ENV_VAR)
        extra_args = resolve_extra_args(self._extra_args, merged_env, DOKIMASIA_EXTRA_ARGS_ENV_VAR)
        if provider is not None:
            command.extend(["--provider", provider])
        if model is not None:
            command.extend(["--model", model])
        if thinking is not None:
            command.extend(["--thinking", thinking])
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
        return AgentRunResult(
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            raw_trace_path=stdout_path,
            trace_events=parse_pi_json_events(stdout.splitlines(), self.skills_dir),
            duration_seconds=time.monotonic() - started,
            mcp_calls=parse_pi_mcp_calls(stdout.splitlines(), self.mcp_normalizers),
            timed_out=timed_out,
        )
