from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SERVER_NAME = "doki-ledger"
SCHEMA = "doki-ledger.v1"

LedgerEntry = dict[str, Any]


def record_transaction(state_path: Path | str, *, account: str, amount_cents: int, memo: str = "") -> LedgerEntry:
    """Append a ledger transaction to a pytest-controlled state file."""
    if not account or not account.strip():
        raise ValueError("account is required")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise ValueError("amount_cents must be an integer")

    path = Path(state_path)
    state = _read_state(path)
    entries = state["entries"]
    sequence = len(entries) + 1
    entry: LedgerEntry = {
        "id": f"txn-{sequence:06d}",
        "sequence": sequence,
        "account": account.strip(),
        "amount_cents": amount_cents,
        "memo": memo,
    }
    entries.append(entry)
    _write_state(path, state)
    return entry


def read_entries(state_path: Path | str) -> list[LedgerEntry]:
    """Read ledger entries for independent oracle assertions."""
    return list(_read_state(Path(state_path))["entries"])


def balance_cents(state_path: Path | str, account: str) -> int:
    """Calculate an account balance from persisted ledger state."""
    return sum(entry["amount_cents"] for entry in read_entries(state_path) if entry["account"] == account)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"server": SERVER_NAME, "schema": SCHEMA, "entries": []}

    with path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    if state.get("server") != SERVER_NAME:
        raise ValueError(f"not a {SERVER_NAME} state file: {path}")
    if state.get("schema") != SCHEMA:
        raise ValueError(f"unsupported {SERVER_NAME} schema in {path}")
    if not isinstance(state.get("entries"), list):
        raise ValueError(f"invalid {SERVER_NAME} state file: entries must be a list")
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, sort_keys=True)
        file.write("\n")
    os.replace(tmp_path, path)
