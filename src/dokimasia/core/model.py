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
    server: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Any = None
    order: int | None = None
    raw: Any = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


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
