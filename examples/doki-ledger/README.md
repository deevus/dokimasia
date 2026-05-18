# doki-ledger

`doki-ledger` is a tiny stateful MCP server for Dokimasia acceptance-test examples.
It exists so MCP evidence work can use a local server that mutates state without
external services, credentials, network cleanup, or a live agent requirement.

The server exposes a ledger-style mutating tool:

- `record_transaction(account, amount_cents, memo?)` appends a transaction to a
  JSON state file controlled by the pytest suite.

It also exposes read-only oracle helpers through MCP:

- `list_entries()`
- `get_balance(account)`

Acceptance tests should verify business state by reading the pytest-controlled
JSON state file with `dokimasia.examples.doki_ledger.read_entries()` or
`balance_cents()`. Later MCP evidence tests can separately assert that an agent
called the MCP tool.

## MCP config fragment

```python
from pathlib import Path

from dokimasia.examples.doki_ledger import mcp_server_config

config = mcp_server_config(Path("/tmp/doki-ledger.json"))
```

This returns a server named `doki-ledger` that runs the local stdio server:

```json
{
  "doki-ledger": {
    "command": "python",
    "args": ["-m", "dokimasia.examples.doki_ledger.server", "--state", "/tmp/doki-ledger.json"]
  }
}
```

The actual `command` value is `sys.executable` so pytest and live-agent examples
use the same Python environment.

## Direct deterministic use

```python
from dokimasia.examples.doki_ledger import balance_cents, record_transaction

record_transaction(state_path, account="supplies", amount_cents=4200, memo="paper")
assert balance_cents(state_path, "supplies") == 4200
```

No live-agent test is included here. Future live-agent examples should be marked
opt-in, for example with `pytest.mark.agent_e2e`, so normal CI remains local and
deterministic.
