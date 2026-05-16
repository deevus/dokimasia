from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json
import os
import stat
import sys

from dokimasia.suite.env import env_with_path_prepend


@dataclass(frozen=True)
class FileSpy:
    wrapper_path: Path
    real_executable: Path
    invocation_name: str
    source: str
    audit_log_env_var: str
    extra_event_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandSpy:
    bin_dir: Path
    audit_log: Path
    real_executable: Path
    executable_name: str
    source: str
    extra_event_fields: Mapping[str, Any] = field(default_factory=dict)

    @property
    def path_prefix(self) -> str:
        return str(self.bin_dir)

    def env_with_path(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        return env_with_path_prepend(self.path_prefix, base_env)


def _validate_executable_name(executable_name: str) -> None:
    if not executable_name:
        raise ValueError("executable_name must not be empty")
    if executable_name in {".", ".."}:
        raise ValueError(f"executable_name must be a file name, not a directory alias: {executable_name!r}")
    if Path(executable_name).name != executable_name:
        raise ValueError(f"executable_name must be a file name, not a path: {executable_name!r}")
    if os.sep in executable_name or "\\" in executable_name:
        raise ValueError(f"executable_name must not contain path separators: {executable_name!r}")
    if os.altsep and os.altsep in executable_name:
        raise ValueError(f"executable_name must not contain path separators: {executable_name!r}")
    if os.pathsep in executable_name:
        raise ValueError(f"executable_name must not contain PATH separators: {executable_name!r}")


def _validate_file_spy_paths(wrapper_path: Path, real_executable: Path) -> None:
    if not real_executable.exists():
        raise ValueError(f"real_executable does not exist: {real_executable}")
    if not real_executable.is_file():
        raise ValueError(f"real_executable must be a file: {real_executable}")
    if wrapper_path.exists() and wrapper_path.is_dir():
        raise ValueError(f"wrapper_path must be a file path, not a directory: {wrapper_path}")
    if wrapper_path == real_executable:
        raise ValueError("wrapper_path must not be the same file as real_executable")
    if wrapper_path.parent.exists() and not wrapper_path.parent.is_dir():
        raise ValueError(f"wrapper_path parent must be a directory: {wrapper_path.parent}")


def create_file_spy(
    *,
    wrapper_path: Path,
    real_executable: Path,
    invocation_name: str,
    source: str,
    audit_log_env_var: str = "DOKIMASIA_COMMAND_LOG",
    extra_event_fields: Mapping[str, Any] | None = None,
) -> FileSpy:
    """Create a Python file-level spy wrapper for a repo-relative action script."""

    if not invocation_name:
        raise ValueError("invocation_name must not be empty")
    if not source:
        raise ValueError("source must not be empty")
    if not audit_log_env_var:
        raise ValueError("audit_log_env_var must not be empty")

    wrapper_path = Path(wrapper_path).resolve()
    real_executable = Path(real_executable).resolve()
    _validate_file_spy_paths(wrapper_path, real_executable)

    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    extra_fields = dict(extra_event_fields or {})
    extra_fields_json = json.dumps(extra_fields, sort_keys=True)
    wrapper_path.write_text(
        f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

real = {str(real_executable)!r}
audit_env_var = {audit_log_env_var!r}
invocation_name = {invocation_name!r}
source = {source!r}
extra_event_fields = json.loads({extra_fields_json!r})
argv = sys.argv[1:]
audit_value = os.environ.get(audit_env_var)
if not audit_value:
    raise RuntimeError(f"{{audit_env_var}} is required for file spy wrapper {{__file__}}")
proc = subprocess.run([sys.executable, real] + argv, text=False)
event = dict(extra_event_fields)
event.update({{
    "action": invocation_name,
    "source": source,
    "argv": argv,
    "cwd": os.getcwd(),
    "pid": os.getpid(),
    "phase": "finish",
    "exit_code": proc.returncode,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}})
audit = Path(audit_value)
audit.parent.mkdir(parents=True, exist_ok=True)
with audit.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(event, sort_keys=True) + "\\n")
raise SystemExit(proc.returncode)
""",
        encoding="utf-8",
    )
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return FileSpy(
        wrapper_path=wrapper_path,
        real_executable=real_executable,
        invocation_name=invocation_name,
        source=source,
        audit_log_env_var=audit_log_env_var,
        extra_event_fields=extra_fields,
    )


def create_spy(
    root: Path,
    executable_name: str,
    real_executable: Path,
    audit_log: Path,
    source: str,
    extra_event_fields: Mapping[str, Any] | None = None,
    audit_log_env_var: str | None = None,
) -> CommandSpy:
    _validate_executable_name(executable_name)

    root = Path(root).resolve()
    real_executable = Path(real_executable).resolve()
    audit_log = Path(audit_log).resolve()

    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    audit_log.parent.mkdir(parents=True, exist_ok=True)

    extra_fields = dict(extra_event_fields or {})
    extra_fields_json = json.dumps(extra_fields, sort_keys=True)
    audit_log_env_var_json = json.dumps(audit_log_env_var)
    wrapper = bin_dir / executable_name
    wrapper.write_text(
        f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

real = {str(real_executable)!r}
default_audit = Path({str(audit_log)!r})
audit_env_var = json.loads({audit_log_env_var_json!r})
source = {source!r}
extra_event_fields = json.loads({extra_fields_json!r})
audit = Path(os.environ.get(audit_env_var, str(default_audit))) if audit_env_var else default_audit
argv = sys.argv[1:]
proc = subprocess.run([real] + argv, text=False)
event = dict(extra_event_fields)
event.update({{
    "source": source,
    "argv": argv,
    "cwd": os.getcwd(),
    "pid": os.getpid(),
    "phase": "finish",
    "exit_code": proc.returncode,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}})
audit.parent.mkdir(parents=True, exist_ok=True)
with audit.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(event, sort_keys=True) + "\\n")
raise SystemExit(proc.returncode)
""",
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return CommandSpy(
        bin_dir=bin_dir,
        audit_log=audit_log,
        real_executable=real_executable,
        executable_name=executable_name,
        source=source,
        extra_event_fields=extra_fields,
    )


__all__ = ["CommandSpy", "FileSpy", "create_file_spy", "create_spy"]
