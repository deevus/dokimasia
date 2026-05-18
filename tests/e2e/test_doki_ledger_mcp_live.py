from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter
from dokimasia.examples.doki_ledger import mcp_server_config, read_entries
from dokimasia.pytest import assert_mcp_called
from tests.e2e.live_support import (
    e2e_run_id as shared_e2e_run_id,
    e2e_run_root as shared_e2e_run_root,
    live_agent_names,
    skip_if_executable_missing,
    skip_if_help_lacks_flag,
    timeout_seconds,
    truthy_env,
)

ENABLE_ENV_VAR = "DOKIMASIA_LIVE_MCP_E2E"
AGENTS_ENV_VAR = "DOKIMASIA_LIVE_MCP_AGENTS"
TIMEOUT_ENV_VAR = "DOKIMASIA_LIVE_MCP_TIMEOUT_SECONDS"
ARTIFACT_DIR_ENV_VAR = "DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR"

SERVER_NAME = "doki-ledger"
TOOL_NAME = "record_transaction"
ACCOUNT = "acceptance"
AMOUNT_CENTS = 1234
MEMO = "opt-in ledger MCP E2E"

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.agent_e2e,
    pytest.mark.mcp_e2e,
    pytest.mark.skipif(
        not truthy_env(ENABLE_ENV_VAR),
        reason=f"set {ENABLE_ENV_VAR}=1 to run live doki-ledger MCP E2E tests",
    ),
]


def e2e_run_id() -> str:
    return shared_e2e_run_id()


def e2e_run_root(run_id: str) -> Path:
    return shared_e2e_run_root(root=ROOT, artifact_dir_env_var=ARTIFACT_DIR_ENV_VAR, run_id=run_id)


@pytest.mark.parametrize("agent_name", live_agent_names(AGENTS_ENV_VAR))
def test_live_agent_records_ledger_transaction_via_mcp(doki_factory, agent_name: str):
    run_id = f"{e2e_run_id()}-{agent_name}"
    run_root = e2e_run_root(run_id)
    state_path = run_root / "ledger.json"
    mcp_config_path = run_root / "mcp.json"
    workspace = run_root / "workspace"
    artifact_dir = run_root / "artifacts"
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_mcp_config(mcp_config_path, state_path)

    adapter = _adapter_for(agent_name, mcp_config_path, run_root)
    prompt = _record_transaction_prompt()

    doki = doki_factory(
        agent=adapter,
        workspace=workspace,
        artifact_dir=artifact_dir,
        run_id=run_id,
        timeout_seconds=timeout_seconds(TIMEOUT_ENV_VAR),
    )
    result = doki.run(prompt, artifact_name=f"{agent_name} ledger mcp")

    assert result.ok, result.failure_summary
    assert_mcp_called(
        result,
        server=SERVER_NAME,
        tool=TOOL_NAME,
        success=True,
        times=1,
        where=_has_expected_transaction_arguments,
    )
    assert read_entries(state_path) == [
        {
            "id": "txn-000001",
            "sequence": 1,
            "account": ACCOUNT,
            "amount_cents": AMOUNT_CENTS,
            "memo": MEMO,
        }
    ]


def _write_mcp_config(config_path: Path, state_path: Path) -> None:
    config = {"mcpServers": mcp_server_config(state_path)}
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _adapter_for(agent_name: str, mcp_config_path: Path, run_root: Path) -> Any:
    if agent_name == "claude":
        return _claude_adapter(mcp_config_path)
    if agent_name == "pi":
        return _pi_adapter(mcp_config_path, run_root)
    raise ValueError(f"unsupported {AGENTS_ENV_VAR} value: {agent_name!r}; use claude, pi, or all")


def _claude_adapter(mcp_config_path: Path) -> ClaudeCodeAdapter:
    claude_bin = skip_if_executable_missing("claude", "Claude Code doki-ledger MCP")
    skip_if_help_lacks_flag(claude_bin, "--mcp-config", "Claude Code")
    return ClaudeCodeAdapter(
        claude_bin=claude_bin,
        extra_args=["--mcp-config", str(mcp_config_path), "--strict-mcp-config"],
    )


def _pi_adapter(mcp_config_path: Path, run_root: Path) -> PiAdapter:
    pi_bin = skip_if_executable_missing("pi", "Pi doki-ledger MCP")
    skip_if_help_lacks_flag(pi_bin, "--mcp-config", "Pi with nicobailon/pi-mcp-adapter")

    skills_dir = run_root / "skills"
    skills_dir.mkdir()
    return PiAdapter(
        pi_bin=pi_bin,
        skills_dir=skills_dir,
        extra_args=["--mcp-config", str(mcp_config_path), "--tools", "mcp"],
    )


def _record_transaction_prompt() -> str:
    return f"""
Use the {SERVER_NAME} MCP server to record exactly one ledger transaction.

Transaction fields:
- account: {ACCOUNT}
- amount_cents: {AMOUNT_CENTS}
- memo: {MEMO}

Do not edit any files directly. Use the MCP tool, then reply with the transaction id only.
""".strip()


def _has_expected_transaction_arguments(call: Any) -> bool:
    return call.arguments == {
        "account": ACCOUNT,
        "amount_cents": AMOUNT_CENTS,
        "memo": MEMO,
    }
