from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    name: str | None = None
    tool: str | None = None
    text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEvent:
    root: str
    argv: list[str]
    cwd: str
    exit_code: int
    mutates: bool
    source: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class McpCall:
    """Normalized MCP operation evidence emitted by an agent adapter."""

    server: str | None = None
    tool: str | None = None
    mode: str = "call"
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    sequence: int | None = None
    call_id: str | None = None
    raw: Any = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class AgentRunResult:
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    raw_trace_path: Path | None
    trace_events: list[TraceEvent]
    duration_seconds: float
    timed_out: bool = False
    commands: list[Any] = field(default_factory=list)

    mcp_calls: list[Any] = field(default_factory=list)
