from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from dokimasia.examples.doki_ledger import balance_cents, mcp_server_config, read_entries, record_transaction


def test_doki_ledger_records_transactions_in_pytest_controlled_state_file(tmp_path: Path):
    state_path = tmp_path / "ledger.json"

    first = record_transaction(state_path, account="travel", amount_cents=1250, memo="train fare")
    second = record_transaction(state_path, account="travel", amount_cents=-250, memo="refund")

    assert first["id"] == "txn-000001"
    assert second["id"] == "txn-000002"
    assert balance_cents(state_path, "travel") == 1000
    assert read_entries(state_path) == [first, second]

    raw_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw_state["server"] == "doki-ledger"
    assert raw_state["entries"] == [first, second]


def test_doki_ledger_exposes_named_mcp_server_config(tmp_path: Path):
    state_path = tmp_path / "ledger.json"

    config = mcp_server_config(state_path)

    assert list(config) == ["doki-ledger"]
    server = config["doki-ledger"]
    assert server["command"] == sys.executable
    assert "dokimasia.examples.doki_ledger.server" in server["args"]
    assert str(state_path) in server["args"]


def test_doki_ledger_stdio_server_lists_and_calls_mutating_tool(tmp_path: Path):
    state_path = tmp_path / "ledger.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dokimasia.examples.doki_ledger.server",
            "--state",
            str(state_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        initialize = _request(process, 1, "initialize", {})
        assert initialize["result"]["serverInfo"]["name"] == "doki-ledger"

        listed = _request(process, 2, "tools/list", {})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert "record_transaction" in tool_names

        called = _request(
            process,
            3,
            "tools/call",
            {
                "name": "record_transaction",
                "arguments": {"account": "supplies", "amount_cents": 4200, "memo": "paper"},
            },
        )

        assert called["result"]["isError"] is False
        assert called["result"]["structuredContent"]["entry"]["id"] == "txn-000001"
        assert balance_cents(state_path, "supplies") == 4200
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _request(process: subprocess.Popen[str], request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, _stderr(process)
    response = json.loads(line)
    assert response["id"] == request_id
    return response


def _stderr(process: subprocess.Popen[str]) -> str:
    if process.stderr is None:
        return ""
    try:
        return process.stderr.read()
    except Exception:
        return ""
