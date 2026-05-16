from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json
import os
import shlex
import shutil
import stat
import subprocess
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
class ShellFileSpy:
    wrapper_path: Path
    real_script: Path
    invocation_name: str
    source: str
    shell_runner: tuple[str, ...]
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


def _validate_file_spy_paths(wrapper_path: Path, real_executable: Path, *, real_label: str = "real_executable") -> None:
    if not real_executable.exists():
        raise ValueError(f"{real_label} does not exist: {real_executable}")
    if not real_executable.is_file():
        raise ValueError(f"{real_label} must be a file: {real_executable}")
    if wrapper_path.exists() and wrapper_path.is_dir():
        raise ValueError(f"wrapper_path must be a file path, not a directory: {wrapper_path}")
    if wrapper_path == real_executable:
        raise ValueError(f"wrapper_path must not be the same file as {real_label}")
    if wrapper_path.parent.exists() and not wrapper_path.parent.is_dir():
        raise ValueError(f"wrapper_path parent must be a directory: {wrapper_path.parent}")


def _resolve_node_runner(node_runner: str | os.PathLike[str]) -> Path:
    try:
        runner_value = os.fspath(node_runner)
    except TypeError as exc:
        raise ValueError("node_runner must be a path-like executable") from exc

    if not runner_value:
        raise ValueError("node_runner must not be empty")
    if "\n" in runner_value or "\r" in runner_value:
        raise ValueError("node_runner must not contain newlines")

    has_path_separator = os.sep in runner_value or (os.altsep is not None and os.altsep in runner_value)
    if has_path_separator:
        runner_path = Path(runner_value).expanduser().resolve()
    else:
        resolved = shutil.which(runner_value)
        if resolved is None:
            raise ValueError(f"node_runner executable not found on PATH: {runner_value}")
        runner_path = Path(resolved).resolve()

    if not runner_path.exists():
        raise ValueError(f"node_runner does not exist: {runner_path}")
    if not runner_path.is_file():
        raise ValueError(f"node_runner must be a file: {runner_path}")
    if not os.access(runner_path, os.X_OK):
        raise ValueError(f"node_runner must be executable: {runner_path}")

    completed = subprocess.run(
        [str(runner_path), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )
    version_output = (completed.stdout + completed.stderr).strip()
    if completed.returncode != 0 or not version_output.startswith("v"):
        raise ValueError(f"node_runner must execute Node.js: {runner_path}")

    return runner_path


def _resolve_real_script(real_script: Path | None, real_executable: Path | None) -> Path:
    if real_script is None and real_executable is None:
        raise ValueError("real_script is required")
    if real_script is not None and real_executable is not None:
        raise ValueError("use either real_script or real_executable, not both")
    return Path(real_script if real_script is not None else real_executable).resolve()


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


def create_node_file_spy(
    *,
    wrapper_path: Path,
    invocation_name: str,
    source: str,
    real_script: Path | None = None,
    real_executable: Path | None = None,
    node_runner: str | os.PathLike[str] = "node",
    audit_log_env_var: str = "DOKIMASIA_COMMAND_LOG",
    extra_event_fields: Mapping[str, Any] | None = None,
) -> FileSpy:
    """Create a JavaScript file-level spy wrapper for a Node action script."""

    if not invocation_name:
        raise ValueError("invocation_name must not be empty")
    if not source:
        raise ValueError("source must not be empty")
    if not audit_log_env_var:
        raise ValueError("audit_log_env_var must not be empty")

    wrapper_path = Path(wrapper_path).resolve()
    real_script_path = _resolve_real_script(real_script, real_executable)
    _validate_file_spy_paths(wrapper_path, real_script_path, real_label="real_script")
    node_runner_path = _resolve_node_runner(node_runner)

    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    extra_fields = dict(extra_event_fields or {})
    extra_fields_json = json.dumps(extra_fields, sort_keys=True)
    wrapper_path.write_text(
        f"""#!{node_runner_path}
'use strict';

const childProcess = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const realScript = {json.dumps(str(real_script_path))};
const nodeRunner = {json.dumps(str(node_runner_path))};
const auditEnvVar = {json.dumps(audit_log_env_var)};
const invocationName = {json.dumps(invocation_name)};
const source = {json.dumps(source)};
const extraEventFields = {extra_fields_json};
const argv = process.argv.slice(2);
const auditValue = process.env[auditEnvVar];

if (!auditValue) {{
  throw new Error(`${{auditEnvVar}} is required for node file spy wrapper ${{__filename}}`);
}}

const proc = childProcess.spawnSync(nodeRunner, [realScript, ...argv], {{stdio: 'inherit'}});
if (proc.error) {{
  throw proc.error;
}}

const exitCode = proc.status === null ? 1 : proc.status;
const event = {{
  ...extraEventFields,
  action: invocationName,
  source,
  argv,
  cwd: process.cwd(),
  pid: process.pid,
  phase: 'finish',
  exit_code: exitCode,
  timestamp: new Date().toISOString(),
}};
fs.mkdirSync(path.dirname(auditValue), {{recursive: true}});
fs.appendFileSync(auditValue, `${{JSON.stringify(event)}}\n`, 'utf8');
process.exit(exitCode);
""",
        encoding="utf-8",
    )
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return FileSpy(
        wrapper_path=wrapper_path,
        real_executable=real_script_path,
        invocation_name=invocation_name,
        source=source,
        audit_log_env_var=audit_log_env_var,
        extra_event_fields=extra_fields,
    )


def _normalize_shell_runner(shell_runner: str | Path | Sequence[str | Path]) -> tuple[str, ...]:
    if isinstance(shell_runner, str):
        runner_parts = [shell_runner]
    elif isinstance(shell_runner, Path):
        runner_parts = [str(shell_runner)]
    else:
        runner_parts = [str(part) for part in shell_runner]

    if not runner_parts:
        raise ValueError("shell_runner must not be empty")
    if any(not part for part in runner_parts):
        raise ValueError("shell_runner entries must not be empty")

    runner_executable = runner_parts[0]
    if os.sep in runner_executable or (os.altsep and os.altsep in runner_executable):
        runner_path = Path(runner_executable).expanduser()
        if not runner_path.exists():
            raise ValueError(f"shell_runner executable does not exist: {runner_executable}")
        if not runner_path.is_file():
            raise ValueError(f"shell_runner executable must be a file: {runner_executable}")
        if not os.access(runner_path, os.X_OK):
            raise ValueError(f"shell_runner executable must be executable: {runner_executable}")
        runner_parts[0] = str(runner_path.resolve())
    else:
        resolved_runner = shutil.which(runner_executable)
        if resolved_runner is None:
            raise ValueError(f"shell_runner executable not found on PATH: {runner_executable}")
        runner_parts[0] = resolved_runner

    return tuple(runner_parts)


def create_shell_file_spy(
    *,
    wrapper_path: Path,
    real_script: Path,
    invocation_name: str,
    source: str,
    shell_runner: str | Path | Sequence[str | Path] = "sh",
    audit_log_env_var: str = "DOKIMASIA_COMMAND_LOG",
    extra_event_fields: Mapping[str, Any] | None = None,
) -> ShellFileSpy:
    """Create a shell file-level spy wrapper for a repo-relative action script."""

    if not invocation_name:
        raise ValueError("invocation_name must not be empty")
    if not source:
        raise ValueError("source must not be empty")
    if not audit_log_env_var:
        raise ValueError("audit_log_env_var must not be empty")

    wrapper_path = Path(wrapper_path).resolve()
    real_script = Path(real_script).resolve()
    _validate_file_spy_paths(wrapper_path, real_script, real_label="real_script")
    runner_parts = _normalize_shell_runner(shell_runner)

    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    extra_fields = dict(extra_event_fields or {})
    extra_fields_json = json.dumps(extra_fields, sort_keys=True)
    runner_command = " ".join(shlex.quote(part) for part in runner_parts)
    wrapper_path.write_text(
        f"""#!/bin/sh
{runner_command} {shlex.quote(str(real_script))} "$@"
__doki_exit_code=$?
{shlex.quote(sys.executable)} - "$__doki_exit_code" "$$" "$@" <<'__DOKIMASIA_SHELL_FILE_SPY_LOG__'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

audit_env_var = {audit_log_env_var!r}
invocation_name = {invocation_name!r}
source = {source!r}
extra_event_fields = json.loads({extra_fields_json!r})
exit_code = int(sys.argv[1])
pid = int(sys.argv[2])
argv = sys.argv[3:]
audit_value = os.environ.get(audit_env_var)
if not audit_value:
    raise RuntimeError(f"{{audit_env_var}} is required for shell file spy wrapper")
event = dict(extra_event_fields)
event.update({{
    "action": invocation_name,
    "source": source,
    "argv": argv,
    "cwd": os.getcwd(),
    "pid": pid,
    "phase": "finish",
    "exit_code": exit_code,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}})
audit = Path(audit_value)
audit.parent.mkdir(parents=True, exist_ok=True)
with audit.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(event, sort_keys=True) + "\\n")
__DOKIMASIA_SHELL_FILE_SPY_LOG__
__doki_log_exit_code=$?
if [ "$__doki_log_exit_code" -ne 0 ]; then
    exit "$__doki_log_exit_code"
fi
exit "$__doki_exit_code"
""",
        encoding="utf-8",
    )
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return ShellFileSpy(
        wrapper_path=wrapper_path,
        real_script=real_script,
        invocation_name=invocation_name,
        source=source,
        shell_runner=runner_parts,
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


__all__ = [
    "CommandSpy",
    "FileSpy",
    "ShellFileSpy",
    "create_file_spy",
    "create_node_file_spy",
    "create_shell_file_spy",
    "create_spy",
]
