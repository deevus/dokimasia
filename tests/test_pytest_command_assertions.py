from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dokimasia.core.model import AgentRunResult
from dokimasia.pytest import DokiResult, assert_command_ran, assert_invoked, cmd


TEA_ISSUE_CREATE = cmd.match("tea", pattern=[("issues", "issue"), "create"])


def result_with_commands(*commands):
    return SimpleNamespace(commands=list(commands))


def command(executable: str, argv: list[str], exit_code: int):
    return {"executable": executable, "argv": argv, "exit_code": exit_code}


def action(action_name: str, argv: list[str], exit_code: int):
    return {"action": action_name, "argv": argv, "exit_code": exit_code, "source": "test-action"}


def test_cmd_match_supports_action_invocation_records():
    matcher = cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact")

    invocation = cmd.normalize_invocation(action("actions/issues/lock.py", ["1", "spam"], 0))

    assert invocation.executable == "actions/issues/lock.py"
    assert invocation.source == "test-action"
    assert matcher.matches(invocation)


def test_assert_invoked_matches_path_spy_and_file_spy_invocations():
    lock_action = cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact")
    tea_create = cmd.match("tea", pattern=["issues", "create"], mode="exact")
    result = result_with_commands(
        command("tea", ["issues", "create"], 0),
        action("actions/issues/lock.py", ["1", "spam"], 0),
    )

    assert_invoked(result, tea_create)
    assert_invoked(result, lock_action)


def test_assert_invoked_supports_count_constraints_and_exit_filters():
    lock_action = cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact")
    result = result_with_commands(
        action("actions/issues/lock.py", ["1", "spam"], 0),
        action("actions/issues/lock.py", ["1", "spam"], 2),
    )

    assert_invoked(result, lock_action, times=1, exit="success")
    assert_invoked(result, lock_action, times=1, exit="failure")
    assert_invoked(result, lock_action, times=2, exit="any")

    with pytest.raises(AssertionError, match="expected count == 1"):
        assert_invoked(result, lock_action, times=1, exit="any")


def test_assert_invoked_failure_message_lists_observed_invocations():
    matcher = cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact")
    result = result_with_commands(command("tea", ["issues", "list"], 0))

    with pytest.raises(AssertionError) as raised:
        assert_invoked(result, matcher)

    message = str(raised.value)
    assert "invocation assertion failed for actions/issues/lock.py.1.spam" in message
    assert "expected count >= 1" in message
    assert "actual count 0" in message
    assert "observed invocations:" in message
    assert "tea issues list" in message


def test_assert_command_ran_requires_a_successful_matching_command_by_default():
    result = result_with_commands(
        command("tea", ["issues", "create", "--title", "ok"], 0),
        command("tea", ["issues", "list"], 0),
    )

    assert_command_ran(result, TEA_ISSUE_CREATE)


def test_default_success_filter_does_not_count_failed_matching_commands():
    result = result_with_commands(command("tea", ["issues", "create"], 1))

    with pytest.raises(AssertionError) as raised:
        assert_command_ran(result, TEA_ISSUE_CREATE)

    message = str(raised.value)
    assert "tea.issues.create" in message
    assert "expected count >= 1" in message
    assert "actual count 0" in message
    assert "exit_code=1" in message


def test_times_min_and_max_count_constraints_are_supported():
    result = result_with_commands(
        command("tea", ["issue", "create", "--title", "one"], 0),
        command("tea", ["issues", "create", "--title", "two"], 0),
        command("tea", ["issues", "list"], 0),
    )

    assert_command_ran(result, TEA_ISSUE_CREATE, times=2)
    assert_command_ran(result, TEA_ISSUE_CREATE, min=1)
    assert_command_ran(result, TEA_ISSUE_CREATE, max=2)

    with pytest.raises(AssertionError, match="expected count == 1"):
        assert_command_ran(result, TEA_ISSUE_CREATE, times=1)


def test_times_cannot_be_combined_with_min_or_max():
    result = result_with_commands(command("tea", ["issues", "create"], 0))

    with pytest.raises(ValueError, match="times cannot be combined with min or max"):
        assert_command_ran(result, TEA_ISSUE_CREATE, times=1, min=1)

    with pytest.raises(ValueError, match="times cannot be combined with min or max"):
        assert_command_ran(result, TEA_ISSUE_CREATE, times=1, max=1)


def test_exit_filter_supports_success_failure_and_any():
    result = result_with_commands(
        command("tea", ["issues", "create", "--title", "ok"], 0),
        command("tea", ["issues", "create", "--title", "bad"], 2),
    )

    assert_command_ran(result, TEA_ISSUE_CREATE, times=1, exit="success")
    assert_command_ran(result, TEA_ISSUE_CREATE, times=1, exit="failure")
    assert_command_ran(result, TEA_ISSUE_CREATE, times=2, exit="any")

    with pytest.raises(ValueError, match="exit must be one of"):
        assert_command_ran(result, TEA_ISSUE_CREATE, exit="timeout")


def test_max_zero_exit_any_asserts_command_did_not_run():
    result = result_with_commands(command("tea", ["issues", "list"], 0))

    assert_command_ran(result, TEA_ISSUE_CREATE, max=0, exit="any")

    with pytest.raises(AssertionError, match="expected count <= 0"):
        assert_command_ran(
            result_with_commands(command("tea", ["issues", "create"], 1)), TEA_ISSUE_CREATE, max=0, exit="any"
        )


def test_failure_message_includes_matcher_expectation_actual_and_observed_commands():
    matcher = cmd.match("git", pattern=["push"])
    result = result_with_commands(
        command("git", ["status", "--short"], 0),
        command("tea", ["issues", "create"], 0),
    )

    with pytest.raises(AssertionError) as raised:
        assert_command_ran(result, matcher, min=1)

    message = str(raised.value)
    assert "git.push" in message
    assert "expected count >= 1" in message
    assert "actual count 0" in message
    assert "git status --short" in message
    assert "tea issues create" in message


def test_doki_result_exposes_normalized_observed_commands_without_budget_helpers(tmp_path: Path):
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    agent_result = AgentRunResult(
        exit_code=0,
        stdout_path=stdout,
        stderr_path=stderr,
        raw_trace_path=None,
        trace_events=[],
        duration_seconds=0.01,
        commands=[command("tea", ["issues", "create"], 0)],
    )

    result = DokiResult.from_agent_result(agent_result, tmp_path / "artifacts")

    assert result.commands[0].executable == "tea"
    assert result.commands[0].argv == ["issues", "create"]
    assert not hasattr(result, "command_count")
    assert not hasattr(result, "mutation_budget")
