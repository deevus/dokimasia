from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter

from dokimasia.core.model import AgentRunResult, TraceEvent
from dokimasia.pytest import cmd


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


def test_default_doki_fixture_is_available(doki):
    assert doki.run_id
    assert doki.workspace.exists()
    assert doki.artifact_root.exists()


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
            "env": {"BASE": "1", "RUN": "2"},
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
