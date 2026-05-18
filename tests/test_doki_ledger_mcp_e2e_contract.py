from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_live_ledger_mcp_e2e_tests_are_skipped_by_default():
    env = os.environ.copy()
    env.pop("DOKIMASIA_LIVE_MCP_E2E", None)
    env.pop("DOKIMASIA_LIVE_MCP_AGENTS", None)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "tests/e2e/test_doki_ledger_mcp_live.py"],
        cwd=Path(__file__).parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "skipped" in completed.stdout
    assert "DOKIMASIA_LIVE_MCP_E2E" in completed.stdout


def test_live_ledger_mcp_e2e_documentation_names_opt_in_controls():
    readme = Path(__file__).parents[1] / "tests" / "e2e" / "README.md"

    text = readme.read_text(encoding="utf-8")

    assert "DOKIMASIA_LIVE_MCP_E2E" in text
    assert "DOKIMASIA_LIVE_MCP_AGENTS" in text
    assert "doki-ledger" in text
    assert "DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR" in text
    assert "JSON" in text


def test_live_ledger_mcp_e2e_run_root_defaults_to_repo_artifacts_dir(monkeypatch):
    from tests.e2e import test_doki_ledger_mcp_live

    monkeypatch.delenv("DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR", raising=False)

    run_root = test_doki_ledger_mcp_live.e2e_run_root("abc123")

    assert run_root == test_doki_ledger_mcp_live.ROOT / ".e2e-artifacts" / "abc123"


def test_live_ledger_mcp_e2e_run_root_uses_env_artifact_dir(monkeypatch):
    from tests.e2e import test_doki_ledger_mcp_live

    monkeypatch.setenv("DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR", "/tmp/dokimasia-live-mcp")

    run_root = test_doki_ledger_mcp_live.e2e_run_root("abc123")

    assert run_root == Path("/tmp/dokimasia-live-mcp") / "abc123"
