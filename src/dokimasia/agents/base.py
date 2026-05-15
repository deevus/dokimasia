from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dokimasia.core.model import AgentRunResult

DOKIMASIA_PROVIDER_ENV_VAR = "DOKIMASIA_PROVIDER"
DOKIMASIA_MODEL_ENV_VAR = "DOKIMASIA_MODEL"
DOKIMASIA_THINKING_ENV_VAR = "DOKIMASIA_THINKING"
DOKIMASIA_EXTRA_ARGS_ENV_VAR = "DOKIMASIA_EXTRA_ARGS"


def resolve_option(explicit: str | None, env: Mapping[str, str], env_var: str) -> str | None:
    if explicit is not None:
        return explicit
    value = env.get(env_var)
    return value or None


def resolve_extra_args(
    explicit: Sequence[str] | None,
    env: Mapping[str, str],
    env_var: str = DOKIMASIA_EXTRA_ARGS_ENV_VAR,
) -> tuple[str, ...]:
    if explicit is not None:
        return tuple(explicit)
    value = env.get(env_var)
    if not value:
        return ()
    return tuple(shlex.split(value))


class AgentAdapter(Protocol):
    def run(
        self,
        prompt: str,
        workspace: Path,
        artifact_dir: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> AgentRunResult: ...
