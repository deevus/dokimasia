from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Mapping


def path_with_prepend(directory: str | Path, existing_path: str | None = None) -> str:
    prefix = str(directory)
    path = os.environ.get("PATH", "") if existing_path is None else existing_path
    return prefix if not path else f"{prefix}{os.pathsep}{path}"


def env_with_path_prepend(directory: str | Path, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    env["PATH"] = path_with_prepend(directory, env.get("PATH", ""))
    return env


def require_executable(executable: str, *, search_path: str | None = None) -> Path:
    found = shutil.which(executable, path=search_path)
    if found is None:
        location = f" on PATH {search_path!r}" if search_path is not None else " on PATH"
        raise FileNotFoundError(f"required executable not found{location}: {executable}")
    return Path(found)


__all__ = ["env_with_path_prepend", "path_with_prepend", "require_executable"]
