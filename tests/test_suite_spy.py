from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dokimasia.suite.spy import CommandSpy, FileSpy, create_file_spy, create_spy


def write_real_executable(root: Path, exit_code: int = 0) -> Path:
    real = root / "real_cli.py"
    real.write_text(
        f"""#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

Path(os.environ["REAL_CLI_RECORD"]).write_text(
    json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd()}}, sort_keys=True),
    encoding="utf-8",
)
raise SystemExit({exit_code})
""",
        encoding="utf-8",
    )
    real.chmod(0o755)
    return real


def test_create_spy_creates_executable_wrapper_and_path_environment(tmp_path):
    root = tmp_path
    record_path = root / "real-record.json"
    audit_log = root / "artifacts" / "audit.jsonl"
    real = write_real_executable(root)

    spy = create_spy(
        root=root / "spy",
        executable_name="demo",
        real_executable=real,
        audit_log=audit_log,
        source="demo-source",
    )
    assert isinstance(spy, CommandSpy)

    wrapper = Path(spy.path_prefix) / "demo"
    assert wrapper.exists()
    assert os.access(wrapper, os.X_OK)

    env = spy.env_with_path({"PATH": "/usr/bin", "REAL_CLI_RECORD": str(record_path)})
    assert env["PATH"].split(os.pathsep)[0] == spy.path_prefix

    result = subprocess.run(
        ["demo", "alpha", "beta"],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    expected_cwd = str(root.resolve())
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"argv": ["alpha", "beta"], "cwd": expected_cwd}

    events = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["source"] == "demo-source"
    assert event["argv"] == ["alpha", "beta"]
    assert event["cwd"] == expected_cwd
    assert event["phase"] == "finish"
    assert event["exit_code"] == 0
    assert isinstance(event["pid"], int)
    assert "timestamp" in event


def test_command_spy_records_nonzero_exit_and_preserves_core_fields_over_extra_fields(tmp_path):
    root = tmp_path
    record_path = root / "real-record.json"
    audit_log = root / "audit.jsonl"
    real = write_real_executable(root, exit_code=7)

    spy = create_spy(
        root=root / "spy",
        executable_name="demo",
        real_executable=real,
        audit_log=audit_log,
        source="demo-source",
        extra_event_fields={
            "suite": "unit",
            "exit_code": 999,
            "source": "wrong",
        },
    )

    env = spy.env_with_path(os.environ | {"REAL_CLI_RECORD": str(record_path)})
    result = subprocess.run(["demo", "fail"], cwd=root, env=env, check=False)

    assert result.returncode == 7
    event = json.loads(audit_log.read_text(encoding="utf-8").strip())
    assert event["suite"] == "unit"
    assert event["source"] == "demo-source"
    assert event["exit_code"] == 7


def test_command_spy_uses_absolute_paths_when_invoked_from_another_directory(tmp_path, monkeypatch):
    root = tmp_path
    setup_dir = root / "setup"
    run_dir = root / "run"
    setup_dir.mkdir()
    run_dir.mkdir()
    record_path = root / "real-record.json"

    monkeypatch.chdir(setup_dir)
    write_real_executable(setup_dir)
    spy = create_spy(
        root=Path("spy"),
        executable_name="demo",
        real_executable=Path("real_cli.py"),
        audit_log=Path("audit/audit.jsonl"),
        source="demo-source",
    )

    env = spy.env_with_path(os.environ | {"REAL_CLI_RECORD": str(record_path)})
    result = subprocess.run(["demo", "from-other-cwd"], cwd=run_dir, env=env, check=False)

    assert result.returncode == 0
    assert json.loads(record_path.read_text(encoding="utf-8"))["argv"] == ["from-other-cwd"]
    assert (setup_dir / "audit" / "audit.jsonl").exists()


def test_command_spy_can_wrap_python3_without_shebang_recursion(tmp_path):
    root = tmp_path
    audit_log = root / "audit.jsonl"
    spy = create_spy(
        root=root / "spy",
        executable_name="python3",
        real_executable=Path(sys.executable),
        audit_log=audit_log,
        source="python3",
    )

    result = subprocess.run(
        ["python3", "-c", "print('wrapped interpreter')"],
        env=spy.env_with_path(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "wrapped interpreter"
    assert json.loads(audit_log.read_text(encoding="utf-8").strip())["argv"] == ["-c", "print('wrapped interpreter')"]


def write_real_python_action(root: Path, exit_code: int = 0) -> Path:
    real = root / "real_action.py"
    real.write_text(
        f"""#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

Path(os.environ["REAL_ACTION_RECORD"]).write_text(
    json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd()}}, sort_keys=True),
    encoding="utf-8",
)
raise SystemExit({exit_code})
""",
        encoding="utf-8",
    )
    real.chmod(0o755)
    return real


def test_create_file_spy_creates_python_action_wrapper_for_direct_invocation(tmp_path):
    root = tmp_path
    record_path = root / "real-action-record.json"
    command_log = root / "artifacts" / "commands.jsonl"
    wrapper_path = root / "workspace" / "actions" / "issues" / "lock.py"
    real = write_real_python_action(root)

    spy = create_file_spy(
        wrapper_path=wrapper_path,
        real_executable=real,
        invocation_name="actions/issues/lock.py",
        source="demo-action",
    )

    assert isinstance(spy, FileSpy)
    assert spy.wrapper_path == wrapper_path.resolve()
    assert os.access(wrapper_path, os.X_OK)

    result = subprocess.run(
        [str(wrapper_path), "1", "spam"],
        cwd=root / "workspace",
        env=os.environ | {"REAL_ACTION_RECORD": str(record_path), "DOKIMASIA_COMMAND_LOG": str(command_log)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    expected_cwd = str((root / "workspace").resolve())
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"argv": ["1", "spam"], "cwd": expected_cwd}
    event = json.loads(command_log.read_text(encoding="utf-8").strip())
    assert event["action"] == "actions/issues/lock.py"
    assert event["argv"] == ["1", "spam"]
    assert event["cwd"] == expected_cwd
    assert event["phase"] == "finish"
    assert event["source"] == "demo-action"
    assert event["exit_code"] == 0
    assert isinstance(event["pid"], int)
    assert "timestamp" in event


def test_python_file_spy_works_through_python_interpreter_and_preserves_nonzero_exit(tmp_path):
    root = tmp_path
    record_path = root / "real-action-record.json"
    command_log = root / "commands.jsonl"
    wrapper_path = root / "workspace" / "actions" / "issues" / "lock.py"
    real = write_real_python_action(root, exit_code=12)

    create_file_spy(
        wrapper_path=wrapper_path,
        real_executable=real,
        invocation_name="actions/issues/lock.py",
        source="demo-action",
    )

    result = subprocess.run(
        [sys.executable, str(wrapper_path), "via", "python"],
        cwd=root / "workspace",
        env=os.environ | {"REAL_ACTION_RECORD": str(record_path), "DOKIMASIA_COMMAND_LOG": str(command_log)},
        check=False,
    )

    assert result.returncode == 12
    assert json.loads(record_path.read_text(encoding="utf-8"))["argv"] == ["via", "python"]
    event = json.loads(command_log.read_text(encoding="utf-8").strip())
    assert event["argv"] == ["via", "python"]
    assert event["exit_code"] == 12


def test_create_file_spy_rejects_invalid_paths_before_agent_run(tmp_path):
    root = tmp_path
    missing_real = root / "missing.py"
    real_directory = root / "real-dir"
    real_directory.mkdir()
    wrapper_directory = root / "wrapper-dir"
    wrapper_directory.mkdir()
    real = write_real_python_action(root)

    invalid_cases = [
        {"wrapper_path": root / "wrapper.py", "real_executable": missing_real},
        {"wrapper_path": root / "wrapper.py", "real_executable": real_directory},
        {"wrapper_path": wrapper_directory, "real_executable": real},
        {"wrapper_path": real, "real_executable": real},
    ]

    for kwargs in invalid_cases:
        with pytest.raises(ValueError):
            create_file_spy(
                invocation_name="actions/issues/lock.py",
                source="demo-action",
                **kwargs,
            )


def test_create_spy_rejects_executable_names_that_are_paths(tmp_path):
    root = tmp_path
    real = write_real_executable(root)
    invalid_names = [
        "",
        ".",
        "..",
        "nested/demo",
        "nested\\demo",
        f"nested{os.pathsep}demo",
        "../demo",
    ]
    for executable_name in invalid_names:
        with pytest.raises(ValueError):
            create_spy(
                root=root / "spy",
                executable_name=executable_name,
                real_executable=real,
                audit_log=root / "audit.jsonl",
                source="demo-source",
            )


def test_old_scaffold_spy_namespace_is_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("dokimasia.scaffold.cli_spy")
