from __future__ import annotations

from pathlib import Path

from dokimasia.core.model import AgentRunResult, TraceEvent
from dokimasia.pytest import doki, doki_factory


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



def test_doki_factory_preserves_explicit_falsy_adapter(doki_factory, tmp_path):
    agent = FalsyFakeAdapter()

    result = doki_factory(
        agent=agent,
        workspace=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    ).run("still run")

    assert result.ok is True
    assert [call["prompt"] for call in agent.calls] == ["still run"]


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
