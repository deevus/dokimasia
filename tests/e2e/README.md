# Opt-in live MCP E2E tests

The tests in this directory run real agents against the local `doki-ledger` MCP
server. They are skipped by default so normal CI stays deterministic and does
not require agent credentials or local MCP configuration.

Run them explicitly with:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 uv run pytest -m "agent_e2e and mcp_e2e" tests/e2e -rs
```

By default the suite runs the Claude Code path. Choose adapters with
`DOKIMASIA_LIVE_MCP_AGENTS`:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=claude uv run pytest tests/e2e -rs
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=pi uv run pytest tests/e2e -rs
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=all uv run pytest tests/e2e -rs
```
Artifacts are stored under `.e2e-artifacts/<run-id>/` by default. Override the
artifact directory:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR=/tmp/dokimasia-ledger-mcp uv run pytest tests/e2e -rs
```

Each run root contains `workspace/`, `artifacts/`, `mcp.json`, and `ledger.json`.
Use `DOKIMASIA_LIVE_MCP_TIMEOUT_SECONDS` to override the per-agent timeout.

## Local requirements

- Claude Code tests require the `claude` CLI with `--mcp-config` support and
  working credentials.
- Pi tests require the `pi` CLI plus an MCP extension that exposes
  `--mcp-config`; the default supported extension is
  `nicobailon/pi-mcp-adapter`.

Each test writes a temporary MCP config pointing at the in-repo `doki-ledger`
server. The agent must record one transaction through MCP. The test then checks
both forms of evidence:

1. normalized MCP evidence with `assert_mcp_called(...)`, including decoded
   business arguments; and
2. independent oracle evidence by reading the pytest-controlled JSON ledger
   state file directly.
