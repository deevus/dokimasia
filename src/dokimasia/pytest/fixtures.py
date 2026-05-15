from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest as _pytest
from slugify import slugify

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter
from dokimasia.core.model import AgentRunResult, TraceEvent
from .cmd import CommandInvocation, CommandSpySpec, normalize_invocation
from dokimasia.suite.env import env_with_path_prepend, require_executable
from dokimasia.suite.spy import CommandSpy, create_spy


_BUILT_IN_AGENTS = {
    "claude": ClaudeCodeAdapter,
    "claude-code": ClaudeCodeAdapter,
    "claude_code": ClaudeCodeAdapter,
    "pi": PiAdapter,
}


def _resolve_agent(agent: Any | None) -> Any:
    if agent is None:
        return UnconfiguredAgentAdapter()
    if not isinstance(agent, str):
        return agent

    agent_name = agent.strip().lower()
    try:
        adapter_type = _BUILT_IN_AGENTS[agent_name]
    except KeyError as exc:
        supported = ", ".join(sorted(_BUILT_IN_AGENTS))
        raise ValueError(f"unsupported agent {agent!r}; supported agents: {supported}") from exc
    return adapter_type()


class UnconfiguredAgentAdapter:
    def run(
        self,
        prompt: str,
        workspace: Path,
        artifact_dir: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> AgentRunResult:
        raise RuntimeError("doki.run requires an agent adapter; pass agent=... to doki_factory")


@dataclass(frozen=True)
class DokiResult:
    exit_code: int
    timed_out: bool
    artifact_dir: Path
    stdout_path: Path
    stderr_path: Path
    raw_trace_path: Path | None
    trace_events: list[TraceEvent]
    duration_seconds: float
    commands: list[CommandInvocation] = field(default_factory=list)

    @classmethod
    def from_agent_result(cls, agent_result: AgentRunResult, artifact_dir: Path) -> "DokiResult":
        return cls(
            exit_code=agent_result.exit_code,
            timed_out=agent_result.timed_out,
            artifact_dir=artifact_dir,
            stdout_path=agent_result.stdout_path,
            stderr_path=agent_result.stderr_path,
            raw_trace_path=agent_result.raw_trace_path,
            trace_events=agent_result.trace_events,
            duration_seconds=agent_result.duration_seconds,
            commands=[normalize_invocation(command) for command in getattr(agent_result, "commands", [])],
        )

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    @property
    def stdout_text(self) -> str:
        return self.stdout_path.read_text(encoding="utf-8")

    @property
    def stderr_text(self) -> str:
        return self.stderr_path.read_text(encoding="utf-8")

    @property
    def failure_summary(self) -> str:
        if self.ok:
            return ""

        reason = "agent timed out" if self.timed_out else f"agent exited with exit code {self.exit_code}"
        stderr = self.stderr_text.strip()
        parts = [
            reason,
            f"artifacts: {self.artifact_dir}",
            f"stdout: {self.stdout_path}",
            f"stderr: {self.stderr_path}",
        ]
        if stderr:
            parts.append(f"stderr text: {stderr}")
        return "\n".join(parts)

    def has_skill_loaded(self, name: str, *, exact: bool = False) -> bool:
        for event in self.trace_events:
            if event.kind != "skill.loaded" or event.name is None:
                continue
            if exact and event.name == name:
                return True
            if not exact and (event.name == name or event.name.endswith(f":{name}")):
                return True
        return False


class Doki:
    def __init__(
        self,
        *,
        agent: Any,
        workspace: Path,
        artifact_root: Path,
        run_id: str,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 300,
        command_spies: Sequence[CommandSpy] = (),
    ):
        self.agent = agent
        self.workspace = workspace
        self.artifact_root = artifact_root
        self.run_id = run_id
        self.env = dict(env or {})
        self.timeout_seconds = timeout_seconds
        self.command_spies = tuple(command_spies)
        self._run_count = 0

    def write_file(self, relative_path: str | Path, content: str) -> Path:
        workspace_root = self.workspace.resolve()
        path = (workspace_root / relative_path).resolve()
        try:
            path.relative_to(workspace_root)
        except ValueError as error:
            raise ValueError(f"write_file path must stay inside the workspace: {relative_path}") from error

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run(
        self,
        prompt: str,
        *,
        timeout_seconds: int | None = None,
        env: dict[str, str] | None = None,
        artifact_name: str | None = None,
    ) -> DokiResult:
        self._run_count += 1
        artifact_dir = self.artifact_root / self._artifact_slug(artifact_name)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        run_env = dict(self.env)
        if env:
            run_env.update(env)

        agent_result = self.agent.run(
            prompt,
            self.workspace,
            artifact_dir,
            run_env,
            self.timeout_seconds if timeout_seconds is None else timeout_seconds,
        )
        return DokiResult.from_agent_result(agent_result, artifact_dir)

    def _artifact_slug(self, artifact_name: str | None) -> str:
        run_slug = f"run-{self._run_count}"
        if artifact_name is None:
            return run_slug

        artifact_slug = slugify(artifact_name)
        if not artifact_slug:
            return run_slug
        return f"{run_slug}-{artifact_slug}"


def _node_slug(nodeid: str) -> str:
    return slugify(nodeid.replace("::", " ")) or "doki-test"


def _default_run_id(nodeid: str) -> str:
    return f"{_node_slug(nodeid)}-{uuid4().hex[:8]}"


def _materialize_command_spies(
    *,
    specs: Sequence[CommandSpySpec],
    artifact_root: Path,
    env: dict[str, str],
) -> tuple[dict[str, str], tuple[CommandSpy, ...]]:
    if not specs:
        return env, ()

    seen_executables: set[str] = set()
    for spec in specs:
        if spec.executable in seen_executables:
            raise ValueError(f"duplicate spy executable: {spec.executable}")
        seen_executables.add(spec.executable)

    search_path = env.get("PATH")
    resolved = [(spec, require_executable(spec.executable, search_path=search_path)) for spec in specs]
    spy_root = artifact_root / "spies" / uuid4().hex[:8]
    audit_log = spy_root / "audit.jsonl"
    command_spies = tuple(
        create_spy(
            root=spy_root,
            executable_name=spec.executable,
            real_executable=real_executable,
            audit_log=audit_log,
            source=spec.source,
        )
        for spec, real_executable in resolved
    )
    path_env = env if "PATH" in env else (env | {"PATH": os.environ.get("PATH", "")})
    return env_with_path_prepend(spy_root / "bin", path_env), command_spies


@_pytest.fixture
def doki_factory(request: _pytest.FixtureRequest, tmp_path: Path):
    def factory(
        *,
        agent: Any | None = None,
        workspace: Path | str | None = None,
        artifact_dir: Path | str | None = None,
        env: dict[str, str] | None = None,
        run_id: str | None = None,
        timeout_seconds: int = 300,
        spies: Sequence[CommandSpySpec] = (),
    ) -> Doki:
        workspace_path = Path(workspace) if workspace is not None else tmp_path / "workspace"
        artifact_root = (
            Path(artifact_dir)
            if artifact_dir is not None
            else tmp_path / ".doki-artifacts" / _node_slug(request.node.nodeid)
        )
        workspace_path.mkdir(parents=True, exist_ok=True)
        artifact_root.mkdir(parents=True, exist_ok=True)
        base_env = dict(env or {})
        run_env, command_spies = _materialize_command_spies(
            specs=spies,
            artifact_root=artifact_root,
            env=base_env,
        )
        return Doki(
            agent=_resolve_agent(agent),
            workspace=workspace_path,
            artifact_root=artifact_root,
            run_id=run_id or _default_run_id(request.node.nodeid),
            env=run_env,
            timeout_seconds=timeout_seconds,
            command_spies=command_spies,
        )

    return factory


@_pytest.fixture
def doki(doki_factory) -> Doki:
    return doki_factory()


__all__ = [
    "Doki",
    "DokiResult",
    "UnconfiguredAgentAdapter",
    "doki",
    "doki_factory",
]
