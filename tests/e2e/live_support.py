from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dokimasia.suite.layout import create_run_id, prepare_run_root

DEFAULT_AGENT_NAMES = ["claude"]
ALL_AGENT_NAMES = ["claude", "pi"]
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def truthy_env(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in TRUTHY_ENV_VALUES


def live_agent_names(env_var: str) -> list[str]:
    raw_value = os.environ.get(env_var, ",".join(DEFAULT_AGENT_NAMES))
    names = [name.strip().lower() for name in raw_value.split(",") if name.strip()]
    if not names:
        return list(DEFAULT_AGENT_NAMES)
    if "all" in names:
        return list(ALL_AGENT_NAMES)
    return names


def e2e_run_id() -> str:
    return create_run_id()


def e2e_run_root(*, root: Path, artifact_dir_env_var: str, run_id: str) -> Path:
    base = Path(os.environ.get(artifact_dir_env_var, root / ".e2e-artifacts"))
    return prepare_run_root(base, run_id)


def timeout_seconds(env_var: str, *, default: int = 180) -> int:
    raw_value = os.environ.get(env_var)
    if raw_value is None:
        return default
    return int(raw_value)


def skip_if_executable_missing(name: str, label: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"{name} CLI is required for the {label} E2E test")
    return executable


def skip_if_help_lacks_flag(executable: str, flag: str, label: str) -> None:
    completed = subprocess.run(
        [executable, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if flag not in completed.stdout:
        pytest.skip(f"{label} must support {flag} for this E2E test")
