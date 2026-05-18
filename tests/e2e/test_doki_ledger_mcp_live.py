from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dokimasia.agents.claude_code import ClaudeCodeAdapter
from dokimasia.agents.pi import PiAdapter
from dokimasia.examples.doki_ledger import mcp_server_config, read_entries
from dokimasia.suite.layout import create_run_id, prepare_run_root
from dokimasia.pytest import assert_mcp_called

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


def _live_mcp_e2e_enabled() -> bool:
    value = os.environ.get(ENABLE_ENV_VAR, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


pytestmark = [
    pytest.mark.agent_e2e,
    pytest.mark.mcp_e2e,
    pytest.mark.skipif(
        not _live_mcp_e2e_enabled(),
        reason=f"set {ENABLE_ENV_VAR}=1 to run live doki-ledger MCP E2E tests",
    ),
]


def _live_agent_names() -> list[str]:
    raw_value = os.environ.get(AGENTS_ENV_VAR, "claude")
    names = [name.strip().lower() for name in raw_value.split(",") if name.strip()]
    if not names:
        return ["claude"]
    if "all" in names:
        return ["claude", "pi"]
    return names


def e2e_run_id() -> str:
    return create_run_id()


def e2e_run_root(run_id: str) -> Path:
    base = Path(os.environ.get(ARTIFACT_DIR_ENV_VAR, ROOT / ".e2e-artifacts"))
    return prepare_run_root(base, run_id)


@pytest.mark.parametrize("agent_name", _live_agent_names())
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
        timeout_seconds=_timeout_seconds(),
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
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        pytest.skip("claude CLI is required for the Claude Code doki-ledger MCP E2E test")
    _skip_if_help_lacks_flag(claude_bin, "--mcp-config", "Claude Code")
    return ClaudeCodeAdapter(
        claude_bin=claude_bin,
        extra_args=["--mcp-config", str(mcp_config_path), "--strict-mcp-config"],
    )


def _pi_adapter(mcp_config_path: Path, run_root: Path) -> PiAdapter:
    pi_bin = shutil.which("pi")
    if pi_bin is None:
        pytest.skip("pi CLI is required for the Pi doki-ledger MCP E2E test")
    _skip_if_help_lacks_flag(pi_bin, "--mcp-config", "Pi with nicobailon/pi-mcp-adapter")

    skills_dir = run_root / "skills"
    skills_dir.mkdir()
    return PiAdapter(
        pi_bin=pi_bin,
        skills_dir=skills_dir,
        extra_args=["--mcp-config", str(mcp_config_path), "--tools", "mcp"],
    )


def _skip_if_help_lacks_flag(executable: str, flag: str, label: str) -> None:
    completed = subprocess.run(
        [executable, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if flag not in completed.stdout:
        pytest.skip(f"{label} must support {flag} for the doki-ledger MCP E2E test")


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


def _timeout_seconds() -> int:
    raw_value = os.environ.get(TIMEOUT_ENV_VAR)
    if raw_value is None:
        return 180
    return int(raw_value)
