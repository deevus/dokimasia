# Opt-in live E2E tests

This directory contains opt-in live-agent E2E tests. They are skipped by default
so normal CI stays deterministic and does not require agent credentials, local
MCP configuration, or local skill/plugin setup.

## Live MCP E2E tests

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


## Live helper-skill E2E tests

The helper-skill E2E test runs a real agent against one shared tiny local `helper-stamp`
skill. The prompt gives the run id but does not reveal the helper script path,
state file location, JSON schema, source marker, or checksum recipe. Those live
inside the helper skill and helper action. The same `SKILL.md` is installed as
a Claude Code project skill and passed to Pi as its skill directory.

Run it explicitly with:

```bash
DOKIMASIA_LIVE_SKILL_E2E=1 uv run pytest -m "agent_e2e and skill_e2e" tests/e2e -rs
```

By default the suite runs the Claude Code path. Choose adapters with
`DOKIMASIA_LIVE_SKILL_AGENTS`:

```bash
DOKIMASIA_LIVE_SKILL_E2E=1 DOKIMASIA_LIVE_SKILL_AGENTS=claude uv run pytest tests/e2e/test_helper_skill_live.py -rs
DOKIMASIA_LIVE_SKILL_E2E=1 DOKIMASIA_LIVE_SKILL_AGENTS=pi uv run pytest tests/e2e/test_helper_skill_live.py -rs
DOKIMASIA_LIVE_SKILL_E2E=1 DOKIMASIA_LIVE_SKILL_AGENTS=all uv run pytest tests/e2e/test_helper_skill_live.py -rs
```

Artifacts are stored under `.e2e-artifacts/<run-id>/` by default. Override the
artifact directory:

```bash
DOKIMASIA_LIVE_SKILL_E2E=1 DOKIMASIA_LIVE_SKILL_E2E_ARTIFACT_DIR=/tmp/dokimasia-helper-skill uv run pytest tests/e2e/test_helper_skill_live.py -rs
```

Use `DOKIMASIA_LIVE_SKILL_TIMEOUT_SECONDS` to override the per-agent timeout.

The test checks three forms of evidence:

1. skill evidence with `result.has_skill_loaded(...)`;
2. audited helper action evidence with `assert_invoked(..., times=1)`; and
3. independent oracle evidence by reading the helper action's JSON state file.

This differs from the MCP E2E test: MCP E2E proves normalized MCP tool evidence,
while helper-skill E2E proves a skill-directed helper action side effect.
