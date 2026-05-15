from __future__ import annotations

from datetime import datetime, timezone

from dokimasia.suite.layout import create_run_id, prepare_run_root, prepare_scenario_dir


def test_create_run_id_uses_unix_timestamp_seconds():
    now = datetime.fromtimestamp(1_778_804_624, tz=timezone.utc)

    assert create_run_id(now) == "1778804624"


def test_prepare_run_root_creates_base_run_id_directory(tmp_path):
    base = tmp_path / "artifacts"

    run_root = prepare_run_root(base, "run-123")

    assert run_root == base / "run-123"
    assert run_root.is_dir()


def test_prepare_run_root_creates_run_id_when_omitted(tmp_path):
    base = tmp_path / "artifacts"

    run_root = prepare_run_root(base)

    assert run_root.parent == base
    assert run_root.name.isdigit()
    assert run_root.is_dir()


def test_prepare_scenario_dir_preserves_current_simple_space_hyphen_behavior(tmp_path):
    parent = tmp_path / "artifacts"

    scenario_dir = prepare_scenario_dir(parent, "Create issue")

    assert scenario_dir == parent / "Create-issue"
    assert scenario_dir.is_dir()


def test_prepare_scenario_dir_uses_slug_for_unsafe_names(tmp_path):
    parent = tmp_path / "artifacts"

    scenario_dir = prepare_scenario_dir(parent, "../issue/create: happy path!")

    assert scenario_dir == parent / "issue-create-happy-path"
    assert scenario_dir.is_dir()


def test_prepare_scenario_dir_uses_fallback_for_empty_slug(tmp_path):
    parent = tmp_path / "artifacts"

    scenario_dir = prepare_scenario_dir(parent, "!!!")

    assert scenario_dir == parent / "scenario"
    assert scenario_dir.is_dir()
