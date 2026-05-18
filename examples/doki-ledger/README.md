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
`balance_cents()`. MCP evidence tests should separately assert that an agent
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

## Live-agent E2E use

The live MCP E2E tests are opt-in and live under `tests/e2e/` so normal CI
remains local and deterministic. They run a real agent against `doki-ledger`,
assert normalized MCP evidence, and verify the final JSON state file as an
independent oracle.

```bash
DOKIMASIA_LIVE_MCP_E2E=1 uv run pytest tests/e2e -rs
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR=/tmp/dokimasia-ledger-mcp uv run pytest tests/e2e -rs
```

See `tests/e2e/README.md` for adapter selection and local configuration.
