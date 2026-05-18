from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter
from dokimasia.pytest import assert_invoked, cmd
from dokimasia.suite import create_file_spy
from tests.e2e.live_support import (
    e2e_run_id as shared_e2e_run_id,
    e2e_run_root as shared_e2e_run_root,
    live_agent_names,
    skip_if_executable_missing,
    timeout_seconds,
    truthy_env,
)

ENABLE_ENV_VAR = "DOKIMASIA_LIVE_SKILL_E2E"
AGENTS_ENV_VAR = "DOKIMASIA_LIVE_SKILL_AGENTS"
ARTIFACT_DIR_ENV_VAR = "DOKIMASIA_LIVE_SKILL_E2E_ARTIFACT_DIR"
TIMEOUT_ENV_VAR = "DOKIMASIA_LIVE_SKILL_TIMEOUT_SECONDS"
STATE_ENV_VAR = "DOKIMASIA_HELPER_SKILL_STATE"

ROOT = Path(__file__).resolve().parents[2]
HELPER_FIXTURE_ROOT = ROOT / "tests" / "e2e" / "helper_skill"
HELPER_SKILL_NAME = "helper-stamp"
HELPER_ACTION_NAME = "helper_skill/actions/stamp_helper.py"
HELPER_ACTION = cmd.match(HELPER_ACTION_NAME)
HELPER_SOURCE = "helper-stamp-skill"
HELPER_STAMP_VERSION = "helper-stamp-v1"

pytestmark = [
    pytest.mark.agent_e2e,
    pytest.mark.skill_e2e,
    pytest.mark.skipif(
        not truthy_env(ENABLE_ENV_VAR),
        reason=f"set {ENABLE_ENV_VAR}=1 to run live helper-skill E2E tests",
    ),
]


def e2e_run_id() -> str:
    return shared_e2e_run_id()


def e2e_run_root(run_id: str) -> Path:
    return shared_e2e_run_root(root=ROOT, artifact_dir_env_var=ARTIFACT_DIR_ENV_VAR, run_id=run_id)


def expected_helper_state(run_id: str) -> dict[str, str]:
    stamp = hashlib.sha256(f"{HELPER_STAMP_VERSION}:{run_id}".encode("utf-8")).hexdigest()
    return {"run_id": run_id, "source": HELPER_SOURCE, "stamp": stamp}


def helper_stamp_prompt(run_id: str) -> str:
    return f"""
Use the {HELPER_SKILL_NAME} skill to stamp Dokimasia helper-skill E2E run {run_id}.
Do not create or edit files yourself. Use the helper's approved action, then reply with only done.
""".strip()


@pytest.mark.parametrize("agent_name", live_agent_names(AGENTS_ENV_VAR))
def test_live_agent_uses_helper_skill_for_side_effect(doki_factory, agent_name: str):
    run_id = f"{e2e_run_id()}-{agent_name}"
    run_root = e2e_run_root(run_id)
    workspace = run_root / "workspace"
    artifact_dir = run_root / "artifacts"
    state_path = run_root / "helper-state.json"
    helper_root = prepare_helper_fixture(run_root)
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    prepare_agent_workspace(workspace, helper_root, agent_name)

    adapter = _adapter_for(agent_name, helper_root)
    doki = doki_factory(
        agent=adapter,
        workspace=workspace,
        artifact_dir=artifact_dir,
        run_id=run_id,
        env={STATE_ENV_VAR: str(state_path)},
        timeout_seconds=timeout_seconds(TIMEOUT_ENV_VAR),
    )

    result = doki.run(helper_stamp_prompt(run_id), artifact_name=f"{agent_name} helper skill")

    assert result.ok, result.failure_summary
    assert result.has_skill_loaded(HELPER_SKILL_NAME)
    assert_invoked(result, HELPER_ACTION, times=1)
    assert json.loads(state_path.read_text(encoding="utf-8")) == expected_helper_state(run_id)


def prepare_helper_fixture(run_root: Path) -> Path:
    helper_root = run_root / "helper-skill"
    if helper_root.exists():
        shutil.rmtree(helper_root)
    shutil.copytree(HELPER_FIXTURE_ROOT, helper_root)

    action_path = helper_root / "actions" / "stamp_helper.py"
    create_file_spy(
        wrapper_path=action_path,
        real_executable=HELPER_FIXTURE_ROOT / "actions" / "stamp_helper.py",
        invocation_name=HELPER_ACTION_NAME,
        source="helper-skill-action",
    )
    _render_helper_skill_file(helper_root, action_path)
    return helper_root


def prepare_agent_workspace(workspace: Path, helper_root: Path, agent_name: str) -> None:
    if agent_name != "claude":
        return

    project_skill = workspace / ".claude" / "skills" / HELPER_SKILL_NAME
    project_skill.parent.mkdir(parents=True, exist_ok=True)
    if project_skill.exists():
        shutil.rmtree(project_skill)
    shutil.copytree(helper_root / "skills" / HELPER_SKILL_NAME, project_skill)


def _render_helper_skill_file(helper_root: Path, action_path: Path) -> None:
    skill_path = helper_root / "skills" / HELPER_SKILL_NAME / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    skill_path.write_text(text.replace("{{HELPER_ACTION}}", str(action_path)), encoding="utf-8")


def _adapter_for(agent_name: str, helper_root: Path) -> Any:
    if agent_name == "claude":
        return _claude_adapter()
    if agent_name == "pi":
        return _pi_adapter(helper_root / "skills")
    raise ValueError(f"unsupported {AGENTS_ENV_VAR} value: {agent_name!r}; use claude, pi, or all")


def _claude_adapter() -> ClaudeCodeAdapter:
    claude_bin = skip_if_executable_missing("claude", "Claude Code helper-skill")
    return ClaudeCodeAdapter(claude_bin=claude_bin)


def _pi_adapter(skills_dir: Path) -> PiAdapter:
    pi_bin = skip_if_executable_missing("pi", "Pi helper-skill")
    return PiAdapter(pi_bin=pi_bin, skills_dir=skills_dir, extra_args=["--no-extensions"])
