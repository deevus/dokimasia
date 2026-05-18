from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .ledger import SERVER_NAME, balance_cents, read_entries, record_transaction

PROTOCOL_VERSION = "2024-11-05"


def mcp_server_config(state_path: Path | str) -> dict[str, dict[str, Any]]:
    """Return an MCP config fragment for the local doki-ledger server."""
    return {
        SERVER_NAME: {
            "command": sys.executable,
            "args": [
                "-m",
                "dokimasia.examples.doki_ledger.server",
                "--state",
                str(state_path),
            ],
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the doki-ledger MCP example server")
    parser.add_argument("--state", required=True, type=Path, help="Path to the JSON ledger state file")
    args = parser.parse_args(argv)

    run_stdio_server(args.state, stdin=sys.stdin, stdout=sys.stdout)
    return 0


def run_stdio_server(state_path: Path, *, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        if not line.strip():
            continue
        response = handle_message(state_path, json.loads(line))
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()


def handle_message(state_path: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if request_id is None:
        return None

    try:
        if method == "initialize":
            result = _initialize_result()
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": _tools()}
        elif method == "tools/call":
            result = _call_tool(state_path, params)
        else:
            return _error(request_id, -32601, f"method not found: {method}")
    except Exception as error:
        return _error(request_id, -32603, str(error))

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
    }


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "record_transaction",
            "description": "Append a transaction to the doki-ledger state file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Ledger account name."},
                    "amount_cents": {"type": "integer", "description": "Signed amount in cents."},
                    "memo": {"type": "string", "description": "Optional transaction memo."},
                },
                "required": ["account", "amount_cents"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_entries",
            "description": "List all doki-ledger transactions.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_balance",
            "description": "Calculate the balance for one account in cents.",
            "inputSchema": {
                "type": "object",
                "properties": {"account": {"type": "string", "description": "Ledger account name."}},
                "required": ["account"],
                "additionalProperties": False,
            },
        },
    ]


def _call_tool(state_path: Path, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _tool_error("tool arguments must be an object")

    try:
        if name == "record_transaction":
            entry = record_transaction(
                state_path,
                account=str(arguments.get("account", "")),
                amount_cents=_as_int(arguments.get("amount_cents")),
                memo=str(arguments.get("memo", "")),
            )
            return _tool_result(f"Recorded {entry['id']} in {entry['account']}.", {"entry": entry})
        if name == "list_entries":
            entries = read_entries(state_path)
            return _tool_result(json.dumps(entries, sort_keys=True), {"entries": entries})
        if name == "get_balance":
            account = str(arguments.get("account", ""))
            balance = balance_cents(state_path, account)
            return _tool_result(f"{account} balance: {balance} cents", {"account": account, "balance_cents": balance})
    except Exception as error:
        return _tool_error(str(error))

    return _tool_error(f"unknown tool: {name}")


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("amount_cents must be an integer")
    return value


def _tool_result(text: str, structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"error": message},
        "isError": True,
    }


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    raise SystemExit(main())
