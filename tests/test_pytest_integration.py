from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter

from dokimasia.core.model import AgentRunResult, TraceEvent
from dokimasia.pytest import cmd
from dokimasia.suite import create_file_spy


class FakeAdapter:
    def __init__(self, *, exit_code: int = 0, timed_out: bool = False):
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.calls: list[dict[str, object]] = []

    def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
        self.calls.append(
            {
                "prompt": prompt,
                "workspace": workspace,
                "artifact_dir": artifact_dir,
                "env": dict(env),
                "timeout_seconds": timeout_seconds,
            }
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent.stdout.txt"
        stderr_path = artifact_dir / "agent.stderr.txt"
        raw_trace_path = artifact_dir / "trace.jsonl"
        stdout_path.write_text("agent stdout", encoding="utf-8")
        stderr_path.write_text("agent stderr", encoding="utf-8")
        raw_trace_path.write_text('{"kind":"skill.loaded"}\n', encoding="utf-8")
        return AgentRunResult(
            exit_code=self.exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            raw_trace_path=raw_trace_path,
            trace_events=[TraceEvent(kind="skill.loaded", name="plugin:create-issue")],
            duration_seconds=0.25,
            timed_out=self.timed_out,
        )


class FalsyFakeAdapter(FakeAdapter):
    def __bool__(self):
        return False


class SubprocessAdapter:
    def __init__(self, commands: Sequence[Sequence[str]]):
        self.commands = [list(command) for command in commands]
        self.calls: list[dict[str, object]] = []

    def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
        command = self.commands[len(self.calls)]
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        self.calls.append(
            {
                "prompt": prompt,
                "workspace": workspace,
                "artifact_dir": artifact_dir,
                "env": dict(env),
                "command": command,
            }
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent.stdout.txt"
        stderr_path = artifact_dir / "agent.stderr.txt"
        raw_trace_path = artifact_dir / "trace.jsonl"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        raw_trace_path.write_text("", encoding="utf-8")
        return AgentRunResult(
            exit_code=completed.returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            raw_trace_path=raw_trace_path,
            trace_events=[],
            duration_seconds=0.01,
            timed_out=False,
        )


def _write_python_tool(path: Path, *, exit_code: int = 0, shebang: str | None = None) -> None:
    path.write_text(
        f"{shebang or f'#!{sys.executable}'}\n"
        "from __future__ import annotations\n"
        "import sys\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_argv_recorder(path: Path, output_path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "from __future__ import annotations\n"
        "import json\n"
        "import sys\n"
        f"output_path = {str(output_path)!r}\n"
        "with open(output_path, 'w', encoding='utf-8') as handle:\n"
        "    json.dump(sys.argv[1:], handle)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_default_doki_fixture_is_available(doki):
    assert doki.run_id
    assert doki.workspace.exists()
    assert doki.artifact_root.exists()


def test_consumer_suite_discovers_dokimasia_pytest_fixtures(tmp_path):
    suite = tmp_path / "consumer-suite"
    suite.mkdir()
    (suite / "test_downstream_fixtures.py").write_text(
        """
def test_downstream_suite_can_request_dokimasia_fixtures(doki_factory, doki):
    configured = doki_factory()

    assert configured.workspace.exists()
    assert configured.artifact_root.exists()
    assert doki.workspace.exists()
    assert doki.artifact_root.exists()
""".lstrip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(suite)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_doki_factory_runs_agent_and_returns_artifacted_result(doki_factory, tmp_path):
    agent = FakeAdapter()
    workspace = tmp_path / "workspace"
    artifact_root = tmp_path / "artifacts"

    result = doki_factory(
        agent=agent,
        workspace=workspace,
        artifact_dir=artifact_root,
        env={"BASE": "1"},
        run_id="custom-run",
        timeout_seconds=99,
    ).run("create an issue", timeout_seconds=7, env={"RUN": "2"}, artifact_name="first turn")

    assert agent.calls == [
        {
            "prompt": "create an issue",
            "workspace": workspace,
            "artifact_dir": artifact_root / "run-1-first-turn",
            "env": {
                "BASE": "1",
                "RUN": "2",
                "DOKIMASIA_COMMAND_LOG": str(artifact_root / "run-1-first-turn" / "commands.jsonl"),
            },
            "timeout_seconds": 7,
        }
    ]
    assert result.ok is True
    assert result.artifact_dir == artifact_root / "run-1-first-turn"
    assert result.raw_trace_path == artifact_root / "run-1-first-turn" / "trace.jsonl"
    assert result.trace_events == [TraceEvent(kind="skill.loaded", name="plugin:create-issue")]
    assert result.stdout_path == artifact_root / "run-1-first-turn" / "agent.stdout.txt"
    assert result.stderr_path == artifact_root / "run-1-first-turn" / "agent.stderr.txt"
    assert result.stdout_text == "agent stdout"
    assert result.stderr_text == "agent stderr"
    assert result.failure_summary == ""


def test_doki_run_preserves_adapter_commands_when_no_spies_are_registered(doki_factory, tmp_path):
    class AgentCommandAdapter(FakeAdapter):
        def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
            result = super().run(prompt, workspace, artifact_dir, env, timeout_seconds)
            result.commands = [{"source": "adapter", "argv": ["one"], "exit_code": 0}]
            return result

    result = doki_factory(
        agent=AgentCommandAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("adapter commands")

    assert (result.artifact_dir / "commands.jsonl").exists()
    assert [command.executable for command in result.commands] == ["adapter"]
    assert [command.argv for command in result.commands] == [["one"]]


def test_doki_run_loads_command_log_events_without_registered_path_spies(doki_factory, tmp_path):
    class CommandLogAdapter(FakeAdapter):
        def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
            command_log = Path(env["DOKIMASIA_COMMAND_LOG"])
            command_log.write_text(
                json.dumps(
                    {
                        "action": "actions/issues/lock.py",
                        "argv": ["1", "spam"],
                        "cwd": str(workspace),
                        "exit_code": 0,
                        "phase": "finish",
                        "source": "test-action",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return super().run(prompt, workspace, artifact_dir, env, timeout_seconds)

    result = doki_factory(
        agent=CommandLogAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("adapter command log")

    assert (result.artifact_dir / "commands.jsonl").exists()
    assert [command.executable for command in result.commands] == ["actions/issues/lock.py"]
    assert [command.argv for command in result.commands] == [["1", "spam"]]
    assert result.commands[0].raw["action"] == "actions/issues/lock.py"


def test_python_file_spy_invocations_can_be_asserted_from_doki_result(doki_factory, tmp_path):
    workspace = tmp_path / "workspace"
    wrapper_path = workspace / "actions" / "issues" / "lock.py"
    real_action = tmp_path / "real-lock.py"
    real_action.write_text(
        "from __future__ import annotations\nimport sys\nraise SystemExit(0 if sys.argv[1:] == ['1', 'spam'] else 9)\n",
        encoding="utf-8",
    )

    create_file_spy(
        wrapper_path=wrapper_path,
        real_executable=real_action,
        invocation_name="actions/issues/lock.py",
        source="test-action",
    )

    result = doki_factory(
        agent=SubprocessAdapter([[sys.executable, str(wrapper_path), "1", "spam"]]),
        workspace=workspace,
        artifact_dir=tmp_path / "artifacts",
    ).run("lock issue")

    assert result.exit_code == 0
    cmd.assert_invoked(
        result,
        cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact"),
    )


def test_doki_factory_materializes_static_command_spies(doki_factory, tmp_path):
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    real_tea = host_bin / "tea"
    real_record = tmp_path / "real-tea.json"
    real_tea.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        f"Path({str(real_record)!r}).write_text(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}, sort_keys=True), encoding='utf-8')\n",
        encoding="utf-8",
    )
    real_tea.chmod(0o755)
    artifact_root = tmp_path / "artifacts"

    doki = doki_factory(
        agent=FakeAdapter(),
        artifact_dir=artifact_root,
        env={"PATH": str(host_bin)},
        spies=[cmd.spy("tea")],
    )

    assert len(doki.command_spies) == 1
    assert doki.command_spies[0].real_executable == real_tea
    spy_bin = Path(doki.command_spies[0].path_prefix)
    assert spy_bin.is_relative_to(artifact_root / "spies")
    assert doki.env["PATH"].split(os.pathsep)[0] == str(spy_bin)
    assert (spy_bin / "tea").exists()

    result = subprocess.run(
        ["tea", "issues", "list"],
        cwd=tmp_path,
        env=doki.env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(real_record.read_text(encoding="utf-8")) == {"argv": ["issues", "list"], "cwd": str(tmp_path)}
    events = [json.loads(line) for line in doki.command_spies[0].audit_log.read_text(encoding="utf-8").splitlines()]
    assert events[0]["source"] == "tea"
    assert events[0]["argv"] == ["issues", "list"]


def test_doki_run_captures_spied_commands_in_per_run_command_logs(doki_factory, tmp_path):
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    _write_python_tool(host_bin / "task")
    path = os.pathsep.join([str(host_bin), os.environ.get("PATH", "")])
    artifact_root = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"

    doki = doki_factory(
        agent=SubprocessAdapter([["task", "one"], ["task", "two"]]),
        workspace=workspace,
        artifact_dir=artifact_root,
        env={"PATH": path},
        spies=[cmd.spy("task")],
    )

    first = doki.run("first")
    second = doki.run("second")

    first_log = first.artifact_dir / "commands.jsonl"
    second_log = second.artifact_dir / "commands.jsonl"
    assert first_log.exists()
    assert second_log.exists()
    assert first_log != second_log
    assert [command.argv for command in first.commands] == [["one"]]
    assert [command.argv for command in second.commands] == [["two"]]
    assert first.commands[0].executable == "task"
    assert first.commands[0].source == "task"
    assert first.commands[0].raw["cwd"] == str(workspace)
    assert first.commands[0].exit_code == 0
    assert json.loads(first_log.read_text(encoding="utf-8").strip())["argv"] == ["one"]
    assert json.loads(second_log.read_text(encoding="utf-8").strip())["argv"] == ["two"]


def test_interpreter_invocations_are_logged_only_when_interpreter_is_spied(doki_factory, tmp_path):
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    _write_python_tool(host_bin / "task", shebang="#!/usr/bin/env python3")
    path = os.pathsep.join([str(host_bin), os.environ.get("PATH", "")])

    task_only = doki_factory(
        agent=SubprocessAdapter([["task"]]),
        workspace=tmp_path / "workspace-task-only",
        artifact_dir=tmp_path / "artifacts-task-only",
        env={"PATH": path},
        spies=[cmd.spy("task")],
    )
    with_interpreter = doki_factory(
        agent=SubprocessAdapter([["task"]]),
        workspace=tmp_path / "workspace-with-interpreter",
        artifact_dir=tmp_path / "artifacts-with-interpreter",
        env={"PATH": path},
        spies=[cmd.spy("task"), cmd.spy("python3")],
    )

    task_only_result = task_only.run("task only")
    with_interpreter_result = with_interpreter.run("with interpreter")

    assert [command.executable for command in task_only_result.commands] == ["task"]
    assert sorted(command.executable for command in with_interpreter_result.commands) == ["python3", "task"]


def test_result_has_skill_loaded_matches_loaded_skill_names(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("load create issue skill")

    assert result.has_skill_loaded("plugin:create-issue") is True


def test_result_has_skill_loaded_is_false_when_skill_is_absent(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("load create issue skill")

    assert result.has_skill_loaded("close-issue") is False


def test_result_has_skill_loaded_defaults_to_suffix_tolerant_matching(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("load create issue skill")

    assert result.has_skill_loaded("create-issue") is True


def test_result_has_skill_loaded_exact_requires_full_skill_name(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("load create issue skill")

    assert result.has_skill_loaded("create-issue", exact=True) is False
    assert result.has_skill_loaded("plugin:create-issue", exact=True) is True


def test_doki_factory_preserves_explicit_falsy_adapter(doki_factory, tmp_path):
    agent = FalsyFakeAdapter()

    result = doki_factory(
        agent=agent,
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("still run")

    assert result.ok is True
    assert [call["prompt"] for call in agent.calls] == ["still run"]


def test_default_doki_fixture_does_not_auto_spy_commands(doki):
    assert doki.command_spies == ()
    assert not (doki.artifact_root / "spies").exists()


def test_doki_factory_isolates_spy_bins_per_factory_instance(doki_factory, tmp_path):
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    artifact_root = tmp_path / "artifacts"
    for executable in ["tea", "gh"]:
        tool = host_bin / executable
        tool.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n", encoding="utf-8")
        tool.chmod(0o755)

    first = doki_factory(
        agent=FakeAdapter(),
        artifact_dir=artifact_root,
        env={"PATH": str(host_bin)},
        spies=[cmd.spy("tea")],
    )
    second = doki_factory(
        agent=FakeAdapter(),
        artifact_dir=artifact_root,
        env={"PATH": str(host_bin)},
        spies=[cmd.spy("gh")],
    )

    first_bin = Path(first.command_spies[0].path_prefix)
    second_bin = Path(second.command_spies[0].path_prefix)
    assert first_bin != second_bin
    assert (first_bin / "tea").exists()
    assert not (second_bin / "tea").exists()
    assert (second_bin / "gh").exists()


def test_doki_factory_rejects_duplicate_spy_executables(doki_factory, tmp_path):
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    tool = host_bin / "tea"
    tool.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n", encoding="utf-8")
    tool.chmod(0o755)

    try:
        doki_factory(
            agent=FakeAdapter(),
            artifact_dir=tmp_path / "artifacts",
            env={"PATH": str(host_bin)},
            spies=[cmd.spy("tea"), cmd.spy("tea", source="tea-admin")],
        )
    except ValueError as error:
        assert "duplicate spy executable" in str(error)
        assert "tea" in str(error)
    else:
        raise AssertionError("expected duplicate spy executable to fail during factory setup")


def test_doki_factory_preserves_path_when_no_spies_are_registered(doki_factory, tmp_path):
    configured = doki_factory(
        agent=FakeAdapter(),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        env={"PATH": "/host/bin"},
    )

    assert configured.command_spies == ()
    assert configured.env["PATH"] == "/host/bin"


def test_doki_factory_fails_clearly_when_spy_executable_is_missing(doki_factory, tmp_path):
    try:
        doki_factory(
            agent=FakeAdapter(),
            workspace=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
            env={"PATH": str(tmp_path / "empty-bin")},
            spies=[cmd.spy("missing-tool")],
        )
    except FileNotFoundError as error:
        assert "required executable not found" in str(error)
        assert "missing-tool" in str(error)
    else:
        raise AssertionError("expected missing spy executable to fail during factory setup")


def test_run_id_workspace_and_default_artifact_root_are_stable_for_fixture_instance(doki_factory):
    agent = FakeAdapter()
    doki = doki_factory(agent=agent)

    original_run_id = doki.run_id
    written = doki.write_file("notes/input.txt", "hello")
    first = doki.run("first")
    second = doki.run("second")

    assert doki.run_id == original_run_id
    assert written == doki.workspace / "notes/input.txt"
    assert written.read_text(encoding="utf-8") == "hello"
    assert doki.artifact_root.parent.name == ".doki-artifacts"
    assert doki.artifact_root.name == (
        "tests-test-pytest-integration-py-"
        "test-run-id-workspace-and-default-artifact-root-are-stable-for-fixture-instance"
    )
    assert first.artifact_dir == doki.artifact_root / "run-1"
    assert second.artifact_dir == doki.artifact_root / "run-2"
    assert first.artifact_dir != second.artifact_dir


def test_write_file_rejects_paths_outside_workspace(doki_factory, tmp_path):
    doki = doki_factory(workspace=tmp_path / "workspace")

    for unsafe_path in ["../outside.txt", tmp_path / "outside.txt"]:
        try:
            doki.write_file(unsafe_path, "nope")
        except ValueError as error:
            assert "inside the workspace" in str(error)
        else:
            raise AssertionError(f"expected ValueError for {unsafe_path!r}")

    assert not (tmp_path / "outside.txt").exists()


def test_named_artifacts_remain_isolated_per_run(doki_factory, tmp_path):
    agent = FakeAdapter()
    doki = doki_factory(
        agent=agent,
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    )

    first = doki.run("first", artifact_name="setup phase")
    second = doki.run("second", artifact_name="setup phase")

    assert first.artifact_dir == tmp_path / "artifacts" / "run-1-setup-phase"
    assert second.artifact_dir == tmp_path / "artifacts" / "run-2-setup-phase"
    assert first.artifact_dir != second.artifact_dir


def test_doki_factory_resolves_supported_builtin_agent_names(doki_factory, tmp_path):
    cases = {
        "pi": PiAdapter,
        "claude-code": ClaudeCodeAdapter,
        "claude_code": ClaudeCodeAdapter,
    }

    for name, expected_type in cases.items():
        configured = doki_factory(
            agent=name,
            workspace=tmp_path / f"workspace-{name}",
            artifact_dir=tmp_path / f"artifacts-{name}",
        )

        assert isinstance(configured.agent, expected_type)


def test_doki_factory_accepts_configured_builtin_adapter_instances(doki_factory, tmp_path):
    skills_dir = tmp_path / "project-skills"
    adapter = PiAdapter(pi_bin="project-pi", skills_dir=skills_dir)

    configured = doki_factory(
        agent=adapter,
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    )

    assert configured.agent is adapter
    assert configured.agent.pi_bin == "project-pi"
    assert configured.agent.skills_dir == skills_dir


def test_pi_adapter_passes_configured_model_to_pi_cli(tmp_path):
    pi_bin = tmp_path / "pi"
    argv_path = tmp_path / "pi-argv.json"
    _write_argv_recorder(pi_bin, argv_path)
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    adapter = PiAdapter(
        pi_bin=str(pi_bin),
        skills_dir=skills_dir,
        provider="anthropic",
        model="claude-sonnet-4",
        thinking="high",
        extra_args=["--models", "claude-*"],
    )

    result = adapter.run(
        "use the skill",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={
            "DOKIMASIA_PROVIDER": "deepseek",
            "DOKIMASIA_MODEL": "deepseek/deepseek-v4-flash",
            "DOKIMASIA_THINKING": "low",
            "DOKIMASIA_EXTRA_ARGS": "--ignored true",
        },
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv == [
        "--print",
        "--mode",
        "json",
        "--no-session",
        "--no-skills",
        "--skill",
        str(skills_dir),
        "--provider",
        "anthropic",
        "--model",
        "claude-sonnet-4",
        "--thinking",
        "high",
        "--models",
        "claude-*",
        "use the skill",
    ]


def test_pi_adapter_uses_dokimasia_provider_env_vars(tmp_path, monkeypatch):
    pi_bin = tmp_path / "pi"
    argv_path = tmp_path / "pi-argv.json"
    _write_argv_recorder(pi_bin, argv_path)
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setenv("DOKIMASIA_PROVIDER", "deepseek")
    monkeypatch.setenv("DOKIMASIA_MODEL", "deepseek/deepseek-v3")

    adapter = PiAdapter(pi_bin=str(pi_bin), skills_dir=skills_dir)

    result = adapter.run(
        "use the skill",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={
            "DOKIMASIA_MODEL": "deepseek/deepseek-v4-flash",
            "DOKIMASIA_THINKING": "high",
            "DOKIMASIA_EXTRA_ARGS": '--models "deepseek/*"',
        },
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv == [
        "--print",
        "--mode",
        "json",
        "--no-session",
        "--no-skills",
        "--skill",
        str(skills_dir),
        "--provider",
        "deepseek",
        "--model",
        "deepseek/deepseek-v4-flash",
        "--thinking",
        "high",
        "--models",
        "deepseek/*",
        "use the skill",
    ]


def test_claude_code_adapter_passes_configured_model_to_claude_cli(tmp_path):
    claude_bin = tmp_path / "claude"
    argv_path = tmp_path / "claude-argv.json"
    _write_argv_recorder(claude_bin, argv_path)

    adapter = ClaudeCodeAdapter(claude_bin=str(claude_bin), model="sonnet", extra_args=["--allowedTools", "Read"])

    result = adapter.run(
        "use the skill",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={},
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv == [
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "sonnet",
        "--allowedTools",
        "Read",
        "use the skill",
    ]


def test_claude_code_adapter_uses_dokimasia_model_env_vars(tmp_path, monkeypatch):
    claude_bin = tmp_path / "claude"
    argv_path = tmp_path / "claude-argv.json"
    _write_argv_recorder(claude_bin, argv_path)
    monkeypatch.setenv("DOKIMASIA_MODEL", "sonnet")

    adapter = ClaudeCodeAdapter(claude_bin=str(claude_bin))

    result = adapter.run(
        "use the skill",
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        env={"DOKIMASIA_EXTRA_ARGS": '--allowedTools "Read Write"'},
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv == [
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "sonnet",
        "--allowedTools",
        "Read Write",
        "use the skill",
    ]


def test_claude_code_adapter_rejects_pi_only_env_vars(tmp_path):
    claude_bin = tmp_path / "claude"
    argv_path = tmp_path / "claude-argv.json"
    _write_argv_recorder(claude_bin, argv_path)
    adapter = ClaudeCodeAdapter(claude_bin=str(claude_bin))

    try:
        adapter.run(
            "use the skill",
            workspace=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            env={"DOKIMASIA_PROVIDER": "anthropic"},
            timeout_seconds=5,
        )
    except ValueError as exc:
        assert "DOKIMASIA_PROVIDER and DOKIMASIA_THINKING are only supported for pi agents" in str(exc)
    else:
        raise AssertionError("expected claude-code to reject pi-only environment variables")


def test_doki_factory_passes_model_to_named_builtin_agent(doki_factory, tmp_path):
    pi = doki_factory(
        agent="pi",
        provider="anthropic",
        model="claude-sonnet-4",
        thinking="high",
        extra_args=["--models", "claude-*"],
        workspace=tmp_path / "workspace-pi",
        artifact_dir=tmp_path / "artifacts-pi",
    )
    claude = doki_factory(
        agent="claude-code",
        model="sonnet",
        extra_args=["--allowedTools", "Read"],
        workspace=tmp_path / "workspace-claude",
        artifact_dir=tmp_path / "artifacts-claude",
    )

    assert pi.agent.provider == "anthropic"
    assert pi.agent.model == "claude-sonnet-4"
    assert pi.agent.thinking == "high"
    assert pi.agent.extra_args == ("--models", "claude-*")
    assert claude.agent.model == "sonnet"
    assert claude.agent.extra_args == ("--allowedTools", "Read")


def test_doki_factory_rejects_pi_only_options_for_claude_code(doki_factory, tmp_path):
    try:
        doki_factory(
            agent="claude-code",
            provider="anthropic",
            thinking="high",
            workspace=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    except ValueError as exc:
        assert "provider and thinking are only supported for pi agents" in str(exc)
    else:
        raise AssertionError("expected pi-only provider options with claude-code to fail")


def test_doki_factory_rejects_model_without_named_builtin_agent(doki_factory, tmp_path):
    try:
        doki_factory(
            agent=FakeAdapter(),
            provider="anthropic",
            model="sonnet",
            thinking="high",
            extra_args=["--verbose"],
            workspace=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    except ValueError as exc:
        assert "provider, model, thinking, and extra_args can only be used with named built-in agents" in str(exc)
    else:
        raise AssertionError("expected provider options with custom adapter to fail")


def test_doki_factory_rejects_unknown_agent_names(doki_factory, tmp_path):
    try:
        doki_factory(
            agent="not-a-real-agent",
            workspace=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    except ValueError as exc:
        assert "unsupported agent" in str(exc)
        assert "not-a-real-agent" in str(exc)
    else:
        raise AssertionError("expected unknown agent name to fail")


def test_result_ok_and_failure_summary_report_agent_health_only(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(exit_code=2),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("fail")

    assert result.ok is False
    assert "exit code 2" in result.failure_summary
    assert str(result.artifact_dir) in result.failure_summary
    assert "agent stderr" in result.failure_summary


def test_result_ok_is_false_for_timeout(doki_factory, tmp_path):
    result = doki_factory(
        agent=FakeAdapter(timed_out=True),
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("timeout")

    assert result.ok is False
    assert "timed out" in result.failure_summary
    assert str(result.stderr_path) in result.failure_summary
